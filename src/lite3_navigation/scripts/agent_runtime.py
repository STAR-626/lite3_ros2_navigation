"""Bounded model→tool→actual-result loop on the existing ROS backend thread.
The HTTP worker never mutates ROS state. No shell, filesystem tools or auto-unlock.
"""
from collections import deque
import copy
import json
import time
import uuid
from std_srvs.srv import Trigger
from deepseek_parser import DeepSeekError,strict_json
from deepseek_agent import request_turn
from agent_tools import parse_message,validate_call
from interaction_core import InvalidCommand
from language_worker import LanguageWorker

READ_ONLY={'get_environment','get_object','get_robot_state','list_places'}
MOVEMENT={'approach_object','navigate_to','return_to_start','return_home'}


class AgentRuntime:
    def __init__(self,node):
        self.node=node;self.worker=LanguageWorker();self.flow=None;self.history=deque(maxlen=3)

    def reset_session(self):
        self.cancel('会话切换');self.history.clear()

    def pose(self):
        try:return self.node.pose()
        except ValueError:return None

    def environment(self):
        n=self.node
        if not n.environment:return {'available':False,'message':n.environment_error,'objects':[]}
        scene=n.environment_reader.snapshot()
        return {'available':scene is not None,'source':'Gazebo仿真真值及用户标注，不是视觉识别',
                'frame':'map/world（当前项目对齐）','axes':{'east':'+X','north':'+Y'},
                'objects':n.environment.records(n.places.points,scene)}

    def start(self,text,request):
        n=self.node
        if self.flow or n.busy or n.sending or n.stop_needed:
            n.emit('当前任务尚未结束。可输入“查询状态”或“停止”；新任务请等待。','BUSY',request);return
        if self.worker.thread and self.worker.thread.is_alive():
            n.emit('上一条网络请求仍在结束，停止与状态查询可用。','BUSY',request);return
        self.worker.poll()  # Drain a cancelled old completion before starting a fresh turn.
        current={'request':text,'environment':self.environment(),'robot_pose':self.pose(),
                 'home':n.home,'navigation_gate':'需用户在本地明确开启，工具不自动解锁'}
        messages=[m for turn in self.history for m in turn]
        user={'role':'user','content':json.dumps(current,ensure_ascii=False)};messages.append(user)
        self.flow={'owner':n.owner,'generation':n.generation,'request':request,'text':text,
                   'messages':messages,'history_start':len(messages)-1,'start_pose':current['robot_pose'],
                   'deadline':time.monotonic()+1200,'rounds':0,'calls':deque(),'used_ids':set(),
                   'pending':None,'api':None,'failed':False,'ledger':[],'motion_count':0}
        n.emit('正在理解完整任务；我会查询环境并逐步执行，工具结果返回后再安排下一步。','PARSING',request)
        self.ask()

    def valid(self,f):
        n=self.node
        return self.flow is f and f['owner']==n.owner and f['generation']==n.generation and not n.closing

    def ask(self):
        f=self.flow
        if not f or not self.valid(f):return
        if f['rounds']>=32:
            self.finish('本轮已达到32次模型调用上限；剩余任务未执行。','LIMIT');return
        token=uuid.uuid4().hex;messages=copy.deepcopy(f['messages'])
        if not self.worker.submit(token,lambda:request_turn(messages)):
            self.finish('模型请求尚未结束，请稍后重新输入。','MODEL_ERROR');return
        f['rounds']+=1;f['api']={'token':token,'deadline':time.monotonic()+30.}

    def tick(self):
        f=self.flow;result=self.worker.poll()
        if not f:return
        if not self.valid(f):self.cancel('会话或停止代际已改变');return
        now=time.monotonic()
        if now>f['deadline']:
            self.node.stop('AI整组任务超过20实际分钟，取消剩余步骤。');return
        if f['api'] and now>f['api']['deadline']:
            f['api']=None;self.finish('模型请求超过30实际秒；已执行结果见记录，迟到回复不会执行。','MODEL_ERROR');return
        if result is not None and f['api']and result[0]==f['api']['token']:
            f['api']=None;_,message,error=result
            if error:self.finish(error,'MODEL_ERROR');return
            try:
                message=parse_message(message,'tool_calls'if message.get('tool_calls')else'stop')
                calls=message.get('tool_calls',[])
                if any(c['id']in f['used_ids']for c in calls):raise DeepSeekError('模型重复使用工具调用编号，未重复执行。')
                if len(f['used_ids'])+len(calls)>64:raise DeepSeekError('单任务工具调用超过64次。')
            except (ValueError,TypeError,AttributeError)as error:self.finish(str(error),'MODEL_ERROR');return
            f['messages'].append(message)
            if not calls:self.finish(message['content']);return
            f['used_ids'].update(c['id']for c in calls);f['calls'].extend(calls)
        if f['pending'] and now>f['pending']['deadline']:
            if f['pending']['name']in MOVEMENT:self.node.stop('AI运动工具等待超时，取消剩余任务。',agent_failure=True)
            else:self.complete({'success':False,'message':'工具响应超时，未确认完成。'})
            return
        if not f['pending']and not f['api']and not self.node.stop_needed:
            if f['calls']:self.dispatch(f['calls'].popleft())
            else:self.ask()

    def dispatch(self,call):
        f=self.flow;n=self.node;name=call['function']['name'];args=strict_json(call['function']['arguments'])
        pending={'id':call['id'],'name':name,'args':args,'request':'tool_'+uuid.uuid4().hex,
                 'deadline':time.monotonic()+(180 if name in MOVEMENT else 8)}
        f['pending']=pending
        if f['failed']and name not in READ_ONLY:
            self.complete({'success':False,'message':'本轮运动已失败，仅允许查询和解释；不会自动执行剩余运动/修改操作。'});return
        try:
            validate_call(name,args)
            if name in MOVEMENT:
                if f['motion_count']>=24:raise InvalidCommand('本轮运动步骤超过24次。')
                f['motion_count']+=1
                n.emit('正在执行：'+{'approach_object':'接近物体 '+args.get('object',''),
                     'navigate_to':'前往指定地点','return_to_start':'返回本轮出发位置','return_home':'返回启动原点'}[name],'PROGRESS')
            if name=='get_environment':
                env=self.environment()
                env['objects']=[r for r in env['objects']if ('category'not in args or r['category']==args['category'])and('kind'not in args or r['kind']==args['kind'])]
                self.complete({'success':True,**env});return
            if name=='get_object':
                if not n.environment:raise InvalidCommand(n.environment_error)
                r=n.environment.resolve(args['object'],n.places.points,n.environment_reader.snapshot())
                self.complete({'success':True,'object':r});return
            if name=='list_places':self.complete({'success':True,'places':copy.deepcopy(n.places.points),'home':n.home});return
            if name=='get_robot_state':
                def done(rep):
                    if self.valid(f)and f['pending']is pending:
                        try:value=json.loads(rep.message)
                        except ValueError:self.complete({'success':False,'message':'导航状态格式无效。'});return
                        self.complete({'success':bool(rep.success),'navigation':value,'robot_pose':self.pose(),'home':n.home,'task_start':f['start_pose']})
                def failed(message):
                    if self.valid(f)and f['pending']is pending:self.complete({'success':False,'message':message})
                n.rpc(n.state,Trigger.Request(),done,failed);return
            if name=='delete_places':
                names=list(n.places.points)if args.get('all')else args['names']
                if any(name not in n.places.points for name in names):raise InvalidCommand('有待删除地点不存在，整组未删除。')
                n.places.persist({k:v for k,v in n.places.points.items()if k not in names});n.confirmation=None;n.redraw()
                self.complete({'success':True,'deleted':names});return
            if name=='stop_task':n.stop('模型调用停止工具，取消剩余任务并关闭导航。');return
            if name=='return_to_start':
                if f['start_pose']is None:raise InvalidCommand('本轮出发位置不可用，不能猜测返回位置。')
                command={'action':'route','targets':[{'pose':f['start_pose']}]}
            elif name=='return_home':command={'action':'route','targets':[{'home':True}]}
            elif name=='navigate_to':command={'action':'route','targets':[args]}
            elif name=='approach_object':command={'action':'approach',**args}
            elif name=='save_place':command={'action':'save',**args}
            elif name=='annotate_object':command={'action':'env_label',**args}
            else:raise InvalidCommand('工具未实现。')
            n.command(command,pending['request'])
        except (ValueError,KeyError,TypeError,OSError)as error:self.complete({'success':False,'message':str(error)})

    def on_event(self,message,code,request,data):
        f=self.flow
        if not f or not self.valid(f)or not f['pending']:return
        p=f['pending'];motion=p['name']in MOVEMENT
        if motion:
            if code=='COMPLETED'and request=='':
                self.complete({'success':True,'message':'导航Action确认到达。','final_pose':self.pose(),**p.get('target',{})});return True
            elif code in ('INVALID','REJECTED','NOT_READY','STORAGE_ERROR')and request in ('',p['request']):
                self.complete({'success':False,'message':message})
            elif code=='APPROACH_READY'and request==p['request']:p['target']={k:v for k,v in data.items()if k in ('temporary_target','object_name')}
        elif request==p['request']and code not in ('PARSING','INTERPRETED','PROGRESS'):
            self.complete({'success':code=='OK','message':message,**data})

    def complete(self,result):
        f=self.flow
        if not f or not f['pending']:return
        p=f['pending'];f['pending']=None
        if p['name']in MOVEMENT and not result.get('success'):f['failed']=True
        f['messages'].append({'role':'tool','tool_call_id':p['id'],'content':json.dumps(result,ensure_ascii=False)})
        f['ledger'].append({'tool':p['name'],'arguments':p['args'],'result':result})

    def prepare_stop(self,message,failed=False):
        f=self.flow
        if failed and f and f['pending']and f['pending']['name']in MOVEMENT:
            self.complete({'success':False,'message':message,'navigation_closed':True})
            f['failed']=True;return True
        self.cancel(message);return False

    def rebind(self):
        if self.flow:self.flow['generation']=self.node.generation

    def finish(self,message,code='OK'):
        f=self.flow
        if not f:return
        self.flow=None
        # Store only complete turns (no orphan pending tool calls).
        turn=f['messages'][f['history_start']:]
        if not f['pending']and not f['calls']and code=='OK':
            self.history.append(turn)
            self.trim_history()
        else:
            summary={'role':'assistant','content':json.dumps({'not_completed':message,'actual_results':f['ledger']},ensure_ascii=False)}
            self.history.append([turn[0],summary])
        self.trim_history()
        motion=[r for r in f['ledger']if r['tool']in MOVEMENT]
        proof=''
        if motion:
            proof='\n实际执行记录：'+'；'.join((r['arguments'].get('object')or r['arguments'].get('name')or {'return_home':'启动原点','return_to_start':'本轮出发处'}.get(r['tool'],'坐标目标'))+('：到达成功'if r['result'].get('success')else'：未完成')for r in motion)
        self.node.emit(message+proof,code,f['request'],tool_results=f['ledger'])

    def trim_history(self):
        while self.history and (len(json.dumps(list(self.history),ensure_ascii=False))>80000 or sum(len(t)for t in self.history)>40):
            if len(self.history)>1:self.history.popleft()
            else:
                turn=self.history[0]
                calls={c['id']:c['function']for m in turn for c in m.get('tool_calls',[])}
                facts=[{'tool':calls.get(m.get('tool_call_id'),{}),'result':m['content']}for m in turn if m['role']=='tool']
                summary={'role':'assistant','content':json.dumps({'historical_results':facts,'last_reply':turn[-1].get('content','')},ensure_ascii=False)}
                compact=[turn[0],summary]
                if len(json.dumps(compact,ensure_ascii=False))>80000:self.history.clear()
                else:self.history[0]=compact
                break

    def cancel(self,message):
        f=self.flow;self.flow=None
        if f:
            summary={'role':'assistant','content':json.dumps({'task_canceled':message,'actual_results':f['ledger']},ensure_ascii=False)}
            self.history.append([f['messages'][f['history_start']],summary])
            self.trim_history()
            self.node.emit('AI整组任务已取消：'+message,'AGENT_CANCELED',f['request'])
