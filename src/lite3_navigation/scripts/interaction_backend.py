#!/usr/bin/env python3
"""Rule-mode terminal entry, durable named places and sequential NavigateTask client."""
import hashlib
import json
import math
from pathlib import Path
import time
import uuid
from collections import deque

import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from rclpy.clock import Clock, ClockType
from rclpy.time import Time
from std_msgs.msg import String
from std_srvs.srv import SetBool, Trigger
from tf2_ros import Buffer, TransformListener, TransformException
from lite3_interfaces.action import NavigateTask
from ament_index_python.packages import get_package_prefix
import yaml
from interaction_core import parse, Places, InvalidCommand, resolve, HELP
from place_markers import MarkerWriter
from environment_catalog import EnvironmentCatalog, parse_environment
from environment_reader import EnvironmentReader
from approach_executor import ApproachExecutor
from agent_runtime import AgentRuntime
from approach_geometry import parse_approach,same_object
from deepseek_parser import interpret, validate
from language_worker import LanguageWorker
from language_context import ClarificationContext,normalize_names,describe,navigation_problem


def map_identity(path):
    path=Path(path);metadata=yaml.safe_load(path.read_text())
    image=Path(metadata['image'])
    if not image.is_absolute():image=path.parent/image
    return hashlib.sha256(path.read_bytes()+image.read_bytes()).hexdigest()


class InteractionBackend(Node):
    def __init__(self):
        super().__init__('lite3_interaction')
        self.declare_parameter('places_file',str(Path.home()/'.local/share/lite3_navigation/places.json'))
        self.declare_parameter('map_yaml','')
        self.declare_parameter('language_mode','rules')
        self.declare_parameter('world_sdf','')
        self.declare_parameter('environment_file','')
        self.declare_parameter('agent_tools',False)
        self.language_mode=self.get_parameter('language_mode').value
        if self.language_mode not in ('rules','deepseek'):
            raise InvalidCommand('language_mode必须为rules或deepseek。')
        self.language=LanguageWorker();self.language_request=None;self.dialogue=ClarificationContext()
        key=map_identity(self.get_parameter('map_yaml').value)
        self.places=Places(self.get_parameter('places_file').value,key)
        self.environment=None;self.environment_reader=None;self.environment_error='环境目录未配置。'
        world_file=self.get_parameter('world_sdf').value
        if world_file:
            try:
                self.environment=EnvironmentCatalog(world_file,key,self.get_parameter('environment_file').value or None)
                self.environment_reader=EnvironmentReader(str(Path(get_package_prefix('lite3_navigation'))/'lib/lite3_navigation/environment_transport'),self.environment.world)
                self.environment_error=''
                self.get_logger().info('语义标注文件：'+str(self.environment.path)+'（首次标注时保存）')
            except (OSError,ValueError,KeyError,TypeError) as error:
                self.environment=None;self.environment_error='环境目录未加载：'+str(error)
                self.get_logger().warning(self.environment_error)

        self.markers=MarkerWriter(str(Path(get_package_prefix('lite3_navigation'))/'lib/lite3_navigation/place_marker_transport'),key)
        self.tf=Buffer();self.listener=TransformListener(self.tf,self)
        self.events=self.create_publisher(String,'/lite3/interaction/events',50)
        self.sub=self.create_subscription(String,'/lite3/interaction/input',self.receive,50)
        self.gate=self.create_client(SetBool,'/lite3/set_navigation_enabled')
        self.state=self.create_client(Trigger,'/lite3/get_navigation_state')
        self.lock=self.create_client(SetBool,'/lite3/set_stop')
        self.nav=ActionClient(self,NavigateTask,'/navigate_task')
        self.owner=None;self.beat=0.;self.seen=deque(maxlen=256);self.generation=0
        self.closing=False;self.home=None;self.route=[];self.total=0;self.index=0;self.goal_handle=None
        self.sending=False;self.sent_at=0.;self.busy=False;self.pending=[]
        self.stop_needed=False;self.stop_pending=False;self.stop_next=0.;self.stop_waiters=[]
        self.refresh=0.;self.last_feedback=0.;self.confirmation=None
        self.approach=ApproachExecutor(self)
        self.agent=AgentRuntime(self) if self.language_mode=='deepseek' and self.get_parameter('agent_tools').value else None
        self.timer=self.create_timer(.1,self.tick,clock=Clock(clock_type=ClockType.STEADY_TIME))
        self.get_logger().info('交互后台就绪：'+self.mode_description()+'，等待 ai_console。')

    def emit(self,message,code='OK',request='',session=None,**data):
        payload={'session':session or self.owner or '', 'id':request, 'code':code,'message':message,**data}
        if getattr(self,'agent',None) and self.agent.on_event(message,code,request,data):
            payload['message']='当前导航步骤已完成，AI继续处理整组任务。'
        self.events.publish(String(data=json.dumps(payload,ensure_ascii=False)))

    def pose(self):
        try:
            tf=self.tf.lookup_transform('map','base_footprint',Time())
            stamp=Time.from_msg(tf.header.stamp)
            age=(self.get_clock().now()-stamp).nanoseconds/1e9
            if not -0.2 <= age <= 2.:raise InvalidCommand('当前位置过期，等待有效TF。')
            q=tf.transform.rotation;p=tf.transform.translation
            yaw=math.degrees(math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z)))
            pose=[p.x,p.y,yaw];Places.validate(pose);return pose
        except TransformException as error:raise InvalidCommand('当前位置暂不可用，等待map到base_footprint。') from error

    def rpc(self,client,request,callback,on_error,seconds=6.):
        if not client.service_is_ready():on_error('系统接口尚未就绪');return
        future=client.call_async(request);token={'done':False}
        def done(f):
            if token['done']:return
            token['done']=True
            try:response=f.result()
            except Exception as error:on_error(str(error));return
            try:callback(response)
            except Exception as error:on_error('响应处理失败：'+str(error))
        future.add_done_callback(done)
        self.pending.append((time.monotonic()+seconds,future,token,on_error))

    def receive(self,msg):
        session='';request=''
        try:
            if len(msg.data)>4096:raise InvalidCommand('请求过长。')
            obj=json.loads(msg.data);session=obj['session'];request=obj.get('id','')
            
            if not isinstance(session,str):raise InvalidCommand('会话编号必须是字符串。')
            uuid.UUID(session)
            if not isinstance(request,str) or len(request)>64:raise InvalidCommand('请求编号不合法。')
            kind=obj.get('kind')
            if kind=='connect':
                if self.owner and self.owner!=session:
                    self.emit('另一个交互终端正在连接；请先退出它。','BUSY',request,session);return
                if self.stop_needed:
                    self.emit('停止尚未确认，请等待。','STOPPING',request,session);return
                if self.owner!=session:
                    self.dialogue.clear()
                    if self.agent:self.agent.reset_session()
                self.owner=session;self.closing=False;self.beat=time.monotonic()
                self.emit('已连接。'+self.mode_description()+'。输入“帮助”查看说明。',request=request,language_mode=self.language_mode);return
            if session!=self.owner:
                self.emit('会话未连接或已经失效，请重开ai_console。','NO_SESSION',request,session);return
            self.beat=time.monotonic()
            if kind=='heartbeat':return
            if not request or request in self.seen:return
            self.seen.append(request)
            if kind=='close':
                self.closing=True
                self.stop('交互终端退出：取消剩余任务并关闭导航。',request);return
            if kind!='text':raise InvalidCommand('未知请求类型。')
            self.input_text(obj.get('text'),request)
        except (ValueError,KeyError,TypeError,InvalidCommand) as error:
            self.emit(str(error),'INVALID',request,session)
        except OSError as error:self.emit('地点文件操作失败：'+str(error),'STORAGE_ERROR',request,session)

    def mode_description(self):
        if self.agent:return 'DeepSeek工具模式（查询环境→调用工具→真实结果→下一步）'
        return 'DeepSeek执行模式（模型理解后经本地检查执行）' if self.language_mode=='deepseek' else '规则模式（不调用模型）'

    def input_text(self,text,request):
        if not isinstance(text,str) or not 0<len(text)<=512:
            raise InvalidCommand('请输入1～512个字符。')
        if self.agent:self.agent_input(text,request);return
        approach_command=parse_approach(text)
        if approach_command:self.command(approach_command,request);return
        environment_command=parse_environment(text)
        if environment_command:self.command(environment_command,request);return
        if self.language_mode=='rules':self.command(parse(text),request);return
        # Explicit stop, queries and overwrite confirmation stay local and remain
        # available even while the HTTP worker is busy. Never use substring stop
        # matching that could turn “不要停止” into an unintended command.
        clean=text.strip().rstrip('。！!？?')
        if clean in ('马上停下','立刻停止','立即停止','紧急停止','停车','别动','快停','快停下','马上停止','立刻停下','请停下','请停止','停下来','赶紧停下'):
            self.command({'action':'stop'},request);return
        try:local=parse(text)
        except InvalidCommand:local=None
        if local and local['action'] in ('stop','state','help','list','show','confirm'):
            self.command(normalize_names(local,self.places.points),request);return
        if self.language_request or self.busy or self.sending or self.stop_needed:
            self.emit('正在解析或执行任务。可输入“停止”“查询状态”；新目标请等待。','BUSY',request);return
        token=uuid.uuid4().hex
        snapshot=json.dumps(self.places.points,ensure_ascii=False,sort_keys=True)
        history=self.dialogue.messages();names=list(self.places.points)
        environment=self.environment.context(self.places.points,self.environment_reader.snapshot()) if self.environment else None
        revision=json.dumps(self.environment.annotations,sort_keys=True,ensure_ascii=False) if self.environment else ''
        def model_request():
            return interpret(text,names,history=history,environment=environment) if environment is not None else interpret(text,names,history=history)
        if not self.language.submit(token,model_request):
            self.emit('上一条模型请求仍在结束，请稍后再试；停止与查询仍可用。','BUSY',request);return
        self.language_request={'token':token,'session':self.owner,'request':request,
            'generation':self.generation,'text':text,'places':snapshot,'environment_revision':revision,'deadline':time.monotonic()+30.}
        self.emit('正在由DeepSeek理解；模型结果仍需本地检查。','PARSING',request)

    def agent_input(self,text,request):
        clean=text.strip().rstrip('。！!？?')
        if clean in ('马上停下','立刻停止','立即停止','紧急停止','停车','别动','快停','快停下','马上停止','立刻停下','请停下','请停止','停下来','赶紧停下'):
            self.command({'action':'stop'},request);return
        try:local=parse(text)
        except InvalidCommand:local=None
        if local and local['action'] in ('stop','state','help','confirm','enable'):
            if self.agent.flow and local['action'] in ('confirm','enable'):
                self.emit('当前AI任务尚未结束，请先等待或输入停止。','BUSY',request);return
            self.command(local,request);return
        self.agent.start(text,request)

    def poll_language(self):
        job=self.language_request
        if job and time.monotonic()>job['deadline']:
            self.language_request=None;self.dialogue.clear()
            self.emit('模型请求超过30实际秒，已取消本次输入，不执行迟到结果。','MODEL_ERROR',job['request'],job['session'])
        result=self.language.poll()
        if result is None:return
        token,value,error=result;job=self.language_request
        if not job or token!=job['token']:return
        self.language_request=None
        if (job['session']!=self.owner or job['generation']!=self.generation or self.closing or
            self.stop_needed or time.monotonic()-self.beat>2.5):return
        request=job['request']
        if error:self.dialogue.clear();self.emit(error,'MODEL_ERROR',request);return
        if job['places']!=json.dumps(self.places.points,ensure_ascii=False,sort_keys=True):
            self.dialogue.clear()
            self.emit('解析期间地点记录发生变化，请重新输入。','STALE_CONTEXT',request);return
        revision=json.dumps(self.environment.annotations,sort_keys=True,ensure_ascii=False) if self.environment else ''
        if job.get('environment_revision','')!=revision:
            self.dialogue.clear();self.emit('解析期间语义标注发生变化，请重新输入。','STALE_CONTEXT',request);return
        try:
            value=normalize_names(validate(value),self.places.points)
            if value['action']=='clarify':
                self.dialogue.remember(job['text'],value['message'])
                self.emit(value['message'],'CLARIFY',request);return
            self.dialogue.clear()
            if value['action']=='unsupported':
                self.emit(value['message'],'UNSUPPORTED',request);return
            if value['action']=='confirm':
                self.emit('覆盖地点需要你明确输入“确认覆盖点名”，模型不能代为确认。','CONFIRM_REQUIRED',request);return
            self.emit('理解为：'+describe(value)+'。','INTERPRETED',request,interpreted=value)
            self.command(value,request)
        except (ValueError,KeyError,TypeError) as error:self.dialogue.clear();self.emit(str(error),'INVALID',request)
        except OSError:self.emit('地点文件操作失败，本次未保存。','STORAGE_ERROR',request)

    def command(self,c,request):
        action=c['action']
        if action in ('save','delete','confirm','enable','route','env_label','approach'):self.dialogue.clear()
        if action=='help':
            if self.agent:
                self.emit('DeepSeek工具模式：可以完整描述多步任务，如先去东墙，再去货架1，最后回到出发处。模型可以查询环境和状态，根据实际结果依次调用后台能力，不执行shell。开启导航、停止、查询状态、覆盖确认优先本地处理。模型请求会发送环境位置、当前任务与最近最多3轮工具记录。运动失败后不自动恢复。',request=request);return
            self.emit(('DeepSeek执行模式：可自由表达单个操作或顺序导航；停止、查询、覆盖确认优先本地处理。模型请求发送本句话、待澄清上下文、已保存点名及语义目录，使用API额度。\n' if self.language_mode=='deepseek' else '')+'临时接近：去货架A旁边；去货架A南侧 距离=0.5（米）。不保存地点。环境查询：列出环境；列出类别 货架；查询物体 shelf_1；标注物体 shelf_1 名称=货架A 类别=货架 别名=一号货架 用途=到点巡检；标注地点 点1 类别=检查点。\n'+(HELP.replace('规则模式，未接入大模型。','固定操作示例：') if self.language_mode=='deepseek' else HELP),request=request);return
        if action=='approach':self.approach.start(c,request);return
        if action in ('env_list','env_show','env_label'):
            self.environment_command(c,request);return
        if action=='stop':self.stop('已请求取消当前任务、清空队列并关闭导航。',request);return
        if action=='list':
            self.emit('已保存地点：'+json.dumps(self.places.points,ensure_ascii=False)+'；本次原点：'+str(self.home),request=request);return
        if action=='show':
            name=c['name']
            if name not in self.places.points and self.environment:
                record=self.environment.resolve(name,self.places.points,self.environment_reader.snapshot())
                if record['kind']=='model':
                    self.environment_command({'action':'env_show','object':record['id']},request);return
                name=record['source_name']
            if name not in self.places.points:raise InvalidCommand('尚未设置：'+c['name'])
            c={**c,'name':name}
            self.emit(c['name']+'：'+str(self.places.points[c['name']])+'（米、米、度）',request=request);return
        if action=='delete':
            self.places.delete(c['name']);self.confirmation=None;self.redraw()
            self.emit('已删除：'+c['name']+'；标记更新已排队。',request=request);return
        if action in ('save','confirm'):
            if action=='confirm':
                if not self.confirmation or c['name']!=self.confirmation[0] or time.monotonic()>self.confirmation[2]:
                    raise InvalidCommand('没有对应的覆盖请求，或请求已超过60秒。')
                name,pose,_=self.confirmation
            else:
                name=c['name'];pose=self.pose() if c.get('current') else list(c['pose'])
                if pose[2] is None:pose[2]=self.pose()[2]
                Places.validate(pose)
                if name in self.places.points:
                    self.confirmation=(name,pose,time.monotonic()+60)
                    self.emit('地点已存在；要覆盖为'+str(pose)+'，请在60秒内输入“确认覆盖'+name+'”。','CONFIRM_REQUIRED',request);return
            self.places.save(name,pose);self.confirmation=None;self.redraw()
            self.emit('已保存'+name+'：'+str(pose)+'（米、米、度）；Gazebo GUI标记更新已排队。',request=request);return
        if action=='state':
            generation=self.generation
            def complete(rep):
                if generation==self.generation:
                    self.emit(rep.message+f'；交互队列剩余{len(self.route)}步。'+('；AI整组任务正在执行' if self.agent and self.agent.flow else '')+('；正在验证物体临时接近点' if self.approach.job else '')+('；标记错误：'+self.markers.error if self.markers.error else ''),request=request,queue_remaining=len(self.route),marker_error=self.markers.error)
            def failed(message):
                if generation==self.generation:self.emit(message,'NOT_READY',request)
            self.rpc(self.state,Trigger.Request(),complete,failed);return
        if self.busy or self.sending or self.stop_needed:
            self.emit('已有任务或接口操作正在处理，请等待或输入“停止”。','BUSY',request);return
        if action=='enable':
            self.busy=True;generation=self.generation
            def complete(rep):
                if generation!=self.generation:
                    if rep.success:self.stop_needed=True
                    return
                self.busy=False;self.emit(rep.message,'OK' if rep.success else 'REJECTED',request)
            def failed(message):
                if generation==self.generation:self.busy=False;self.stop('开启响应不确定，已请求重新关闭导航。'+message,request)
            self.rpc(self.gate,SetBool.Request(data=True),complete,failed);return
        if action=='route':
            if self.environment and len(c['targets'])==1 and 'name' in c['targets'][0] and c['targets'][0]['name']not in self.places.points:
                try:record=self.environment.resolve(c['targets'][0]['name'],self.places.points,self.environment_reader.snapshot())
                except InvalidCommand:record=None
                if record and record['kind']=='model':
                    self.approach.start({'action':'approach','object':record['id']},request);return
            yaw=self.pose()[2]
            targets=[dict(t) for t in c['targets']]
            if self.environment:
                scene=self.environment_reader.snapshot()
                for t in targets:
                    if 'name' in t:t['name']=self.environment.place_reference(t['name'],self.places.points,scene)
            route=resolve(targets,self.places.points,self.home,yaw)
            if not self.nav.server_is_ready():raise InvalidCommand('导航任务接口尚未就绪。')
            self.route=route;self.total=len(route);self.index=0;self.busy=True
            self.emit('已解析'+str(self.total)+'个目标，正在检查导航状态；地点坐标已固定。',request=request)
            self.advance();return
        raise InvalidCommand('动作尚未实现。')

    def environment_command(self,c,request):
        if not self.environment:raise InvalidCommand(self.environment_error)
        scene=self.environment_reader.snapshot();action=c['action']
        status='Gazebo实时目录（坐标为世界系米，朝向为度）' if scene is not None else 'Gazebo实时目录不可用；仅列出历史标注/场景定义，物体当前位置未知'
        if action=='env_list':
            records=self.environment.records(self.places.points,scene)
            if 'category' in c:records=[r for r in records if r['category']==c['category']]
            lines=[f"{r['name']} [{r['id']}] 类别={r['category']}，"+('已保存地点' if r['kind']=='place' else ('当前存在' if r['present'] is True else '当前不存在' if r['present'] is False else '存在性待确认')) for r in records]
            self.emit(status+'：\n'+('\n'.join(lines) or '没有匹配项。'),request=request,environment=records);return
        if action=='env_label':
            fields={k:v for k,v in c.items() if k not in ('action','object')}
            record=self.environment.label(c['object'],fields,self.places.points,scene)
            self.emit('语义标注已保存：'+record['name']+' ['+record['id']+']；不改变模型名称、位置或导航目标。',request=request,environment=record);return
        record=self.environment.resolve(c['object'],self.places.points,scene)
        self.emit(status+'：'+json.dumps(record,ensure_ascii=False),request=request,environment=record)

    def advance(self):
        if not self.route:return
        generation=self.generation
        def failure(message):
            if generation!=self.generation:return
            suffix='；本次导航未启动。' if self.index==0 else '；后续导航目标已取消。'
            self.route=[];self.busy=False;self.emit(message+suffix,'REJECTED')
        def checked(rep):
            if generation!=self.generation:return
            try:
                if not rep.success:failure('任务节点未能提供有效状态');return
                problem=navigation_problem(json.loads(rep.message))
                if problem:failure(problem);return
            except (ValueError,KeyError):failure('导航状态格式错误');return
            target=self.route[0];x,y,angle=target['pose']
            self.sending=True;self.sent_at=time.monotonic()
            self.emit(f'开始第{self.index+1}/{self.total}步：{target["label"]}，x={x:g}，y={y:g}，朝向={angle:g}度。')
            future=self.nav.send_goal_async(NavigateTask.Goal(goal_x=float(x),goal_y=float(y),goal_yaw=math.radians(angle)),feedback_callback=self.feedback)
            def accepted(f):
                try:handle=f.result()
                except Exception as error:
                    if generation==self.generation:self.stop('导航提交异常：'+str(error),agent_failure=True)
                    return
                if generation!=self.generation:
                    if handle.accepted:handle.cancel_goal_async();self.stop_needed=True
                    return
                self.sending=False
                if not handle.accepted:failure('任务节点拒绝本目标');return
                self.goal_handle=handle
                handle.get_result_async().add_done_callback(lambda f:self.finished(f,generation))
            future.add_done_callback(accepted)
        self.rpc(self.state,Trigger.Request(),checked,failure)

    def feedback(self,msg):
        if self.goal_handle is None or not self.route:return
        if bytes(msg.goal_id.uuid)!=bytes(self.goal_handle.goal_id.uuid):return
        now=time.monotonic()
        if now-self.last_feedback>1.:
            self.last_feedback=now;self.emit(f'第{self.index+1}/{self.total}步：{msg.feedback.phase}，剩余{msg.feedback.remaining_distance:.2f}米。','PROGRESS')

    def finished(self,future,generation):
        if generation!=self.generation:return
        self.goal_handle=None
        try:
            response=future.result();result=response.result
            if self.approach.watch and not same_object(self.approach.watch,self.approach.object_now(self.approach.watch['name'])):
                self.stop('接近对象已移动或位姿失效，本次到点不能视为完成检查。',agent_failure=True);return
            if response.status!=4 or result.result_code!=0:
                self.stop(f'第{self.index+1}步失败，任务码{result.result_code}：{result.message}；后续任务取消。',agent_failure=True);return
        except Exception as error:self.stop('导航结果异常：'+str(error),agent_failure=True);return
        self.route.pop(0);self.index+=1
        self.emit(f'第{self.index}/{self.total}步到达成功。')
        if self.route:self.advance()
        else:self.busy=False;self.emit('整组任务完成。','COMPLETED')

    def stop(self,message,request='',agent_failure=False):
        retained=self.agent.prepare_stop(message,agent_failure) if self.agent else False
        self.approach.cancel()
        self.generation+=1;self.route=[];self.sending=False;self.busy=False;self.confirmation=None
        self.language_request=None;self.dialogue.clear()
        if self.goal_handle:
            self.goal_handle.cancel_goal_async();self.goal_handle=None
        self.stop_needed=True;self.stop_next=0.
        self.emit(message,'STOPPING',request)
        if retained:self.agent.rebind()

    def tick(self):
        now=time.monotonic()
        expired=[]
        for deadline,future,token,error in self.pending:
            if not token['done'] and now>deadline:
                token['done']=True;expired.append(error)
        self.pending=[p for p in self.pending if not p[2]['done']]
        for error in expired:error('接口响应超时')
        if self.home is None:
            try:self.home=self.pose();self.redraw()
            except InvalidCommand:pass
        if now-self.refresh>3:
            self.refresh=now;self.redraw()
        if self.owner and not self.closing and now-self.beat>2.5:
            old=self.owner;self.stop('交互终端心跳中断，取消队列并关闭导航。')
            self.owner=None;self.emit('会话已失效。','DISCONNECTED',session=old)
        self.approach.tick()
        self.poll_language()
        if self.agent:self.agent.tick()
        if self.sending and now-self.sent_at>6:
            self.stop('导航提交超时；取消后续任务，迟到接受也将被取消。',agent_failure=True)
        if self.stop_needed and not self.stop_pending and now>=self.stop_next:
            self.stop_pending=True;self.stop_next=now+1.
            # Also latch the motion node if mission_manager is unavailable.
            if self.lock.service_is_ready():self.lock.call_async(SetBool.Request(data=True))
            def done(rep):
                self.stop_pending=False
                if rep.success:
                    self.stop_needed=False;self.emit('导航关闭与停止已由任务节点确认。','STOPPED')
                    if self.closing:self.owner=None;self.closing=False
            def failed(message):
                self.stop_pending=False;self.emit('停止尚未确认，将继续重试：'+message,'STOPPING')
            self.rpc(self.gate,SetBool.Request(data=False),done,failed)

    def redraw(self):
        points=dict(self.places.points)
        if self.home is not None:points['原点']=self.home
        self.markers.update(points)


def main():
    rclpy.init();node=None
    try:
        node=InteractionBackend();rclpy.spin(node)
    except KeyboardInterrupt:pass
    finally:
        if node:
            node.approach.cancel()
            if node.environment_reader:node.environment_reader.close()
            node.markers.close();node.destroy_node()
        if rclpy.ok():rclpy.shutdown()


if __name__=='__main__':main()
