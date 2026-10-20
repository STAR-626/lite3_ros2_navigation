#!/usr/bin/env python3
"""Domain220: installed DeepSeek-mode backend; synthetic model/API, mocked tasks; no key/network/robot."""
import json, os, signal, subprocess, tempfile, time, uuid
from pathlib import Path
import rclpy
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.task import Future
from geometry_msgs.msg import TransformStamped
from std_msgs.msg import String
from std_srvs.srv import SetBool, Trigger
from tf2_ros import TransformBroadcaster
from lite3_interfaces.action import NavigateTask


def main():
    assert os.environ.get('ROS_DOMAIN_ID')=='220'
    root=Path(__file__).resolve().parents[3];out=Path(tempfile.mkdtemp(prefix='lite3-deepseek-exec-'))
    rclpy.init();n=rclpy.create_node('interaction_fixture');tf=TransformBroadcaster(n)
    events=[];received=[];state={'enabled':False,'busy':False,'fail':False,'duration':.3,'heartbeats':True,'active':0,'max_active':0,'accept_delay':0.,'accept_waiting':False}
    session=str(uuid.uuid4());pub=n.create_publisher(String,'/lite3/interaction/input',30)
    n.create_subscription(String,'/lite3/interaction/events',lambda m:events.append(json.loads(m.data)),100)
    def send(kind,text='',ident=None):
        ident=ident or uuid.uuid4().hex
        pub.publish(String(data=json.dumps({'session':session,'id':ident,'kind':kind,'text':text},ensure_ascii=False)));return ident
    def timer():
        t=TransformStamped();t.header.frame_id='map';t.child_frame_id='base_footprint';t.header.stamp=n.get_clock().now().to_msg();t.transform.translation.x=-3.;t.transform.translation.y=-4.;t.transform.rotation.w=1.;tf.sendTransform(t)
        if state['heartbeats']:send('heartbeat')
    tick=n.create_timer(.2,timer)
    def gate(req,rep):state['enabled']=req.data;rep.success=True;rep.message='开启'if req.data else'关闭';return rep
    def lock(req,rep):rep.success=True;return rep
    def query(req,rep):rep.success=True;rep.message=json.dumps({'navigation_enabled':state['enabled'],'busy':state['busy'],'fault_latched':False,'switch_pending':False});return rep
    n.create_service(SetBool,'/lite3/set_navigation_enabled',gate)
    n.create_service(SetBool,'/lite3/set_stop',lock)
    n.create_service(Trigger,'/lite3/get_navigation_state',query)
    async def execute(handle):
        state['busy']=True;state['active']+=1;state['max_active']=max(state['max_active'],state['active'])
        received.append([handle.request.goal_x,handle.request.goal_y,handle.request.goal_yaw])
        future=Future();start=time.monotonic();failure=state['fail']
        def finish_tick():
            if not future.done() and (handle.is_cancel_requested or not state['enabled'] or time.monotonic()-start>state['duration']):future.set_result(None)
        t=n.create_timer(.03,finish_tick);await future;n.destroy_timer(t)
        state['busy']=False;state['active']-=1;result=NavigateTask.Result()
        if handle.is_cancel_requested:handle.canceled();result.result_code=7
        elif not state['enabled']:handle.abort();result.result_code=7
        elif failure:handle.abort();result.result_code=2;result.message='模拟受阻'
        else:handle.succeed();result.result_code=0
        return result
    async def accept_goal(req):
        if state['accept_delay']:
            state['accept_waiting']=True;future=Future();start=time.monotonic()
            def ready():
                if not future.done() and time.monotonic()-start>state['accept_delay']:future.set_result(None)
            timer=n.create_timer(.02,ready);await future;n.destroy_timer(timer);state['accept_waiting']=False
        return GoalResponse.ACCEPT
    server=ActionServer(n,NavigateTask,'/navigate_task',execute_callback=execute,goal_callback=accept_goal,cancel_callback=lambda _:CancelResponse.ACCEPT,callback_group=ReentrantCallbackGroup())
    stub=out/'backend_stub.py'
    stub.write_text("""import sys,time
sys.path.insert(0,sys.argv.pop(1))
import importlib.util
from importlib.machinery import SourceFileLoader
loader=SourceFileLoader('interaction_backend',sys.path[0]+'/interaction_backend')
spec=importlib.util.spec_from_loader(loader.name,loader)
backend=importlib.util.module_from_spec(spec);loader.exec_module(backend)
from deepseek_parser import DeepSeekError

def model(text,names,history=None):
    if text=='请开启一下导航':return {'action':'enable'}
    if text=='保存点1':return {'action':'save','name':'点1','pose':[1.,2.,0.]}
    if text=='准备覆盖点1':return {'action':'save','name':'点1','pose':[1.2,2.,0.]}
    if text=='失联慢请求':
        time.sleep(3.3);return {'action':'route','targets':[{'name':'点1'}]}
    if text=='保存点2':return {'action':'save','name':'点2','pose':[2.,3.,90.]}
    if text=='帮我先去点1然后回家':return {'action':'route','targets':[{'name':'点1'},{'home':True}]}
    if text=='缺少信息':return {'action':'clarify','message':'请补充y坐标'}
    if text=='跳桌':return {'action':'unsupported','message':'当前不支持跳跃'}
    if text=='API失败':raise DeepSeekError('模拟API失败')
    if text=='乱输出':return {'action':'shell','command':'ls'}
    if text in ('慢请求','断线慢请求','超时请求'):
        time.sleep(1.5);return {'action':'enable'}
    if text=='规定当前地点是点1或者家':return {'action':'clarify','message':'要保存当前位置还是导航？'}
    if text=='保存为':
        assert history and any('规定当前地点' in m['content']for m in history)
        return {'action':'clarify','message':'要保存为什么名字？'}
    if text=='1':
        assert len(history)==4 and any('保存为' in m['content']for m in history)
        return {'action':'save','name':'点1','current':True}
    if text=='无前文补充':
        assert not history
        return {'action':'clarify','message':'请说完整要求'}
    if text=='去数字一':return {'action':'route','targets':[{'name':'1'}]}
    if text=='代为确认':return {'action':'confirm','name':'点1'}
    raise DeepSeekError('模拟器没有这个输入')

backend.interpret=model
original=backend.InteractionBackend.input_text
def input_text(self,text,request):
    original(self,text,request)
    if text=='超时请求' and self.language_request:self.language_request['deadline']=time.monotonic()+.25
backend.InteractionBackend.input_text=input_text
backend.main()
""")
    log=(out/'backend.log').open('w');proc=subprocess.Popen(['/usr/bin/python3',str(stub),str(root/'install/lite3_navigation/lib/lite3_navigation'),'--ros-args','-p','language_mode:=deepseek','-p','map_yaml:='+str(root/'src/lite3_gazebo/maps/large_warehouse.yaml'),'-p','places_file:='+str(out/'places.json')],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    checks=[]
    def wait(pred,seconds=8):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            rclpy.spin_once(n,timeout_sec=.02)
            if pred():return
        raise AssertionError((out/'backend.log').read_text()[-3000:]+'\nevents:'+str(events[-8:]))
    def command(text,code='OK'):
        ident=send('text',text)
        wait(lambda:any(e.get('id')==ident and e['code']not in ('PARSING','INTERPRETED')for e in events))
        reply=next(e for e in reversed(events)if e.get('id')==ident and e['code']not in ('PARSING','INTERPRETED'))
        assert reply['code']==code,reply;return reply
    def pause(seconds):
        start=time.monotonic();wait(lambda:time.monotonic()-start>seconds,seconds+1)
    try:
        for _ in range(15):
            send('connect',ident='connect');pause(.2)
            if any(e['id']=='connect' and e['code']=='OK'for e in events):break
        wait(lambda:any(e['id']=='connect' and e['code']=='OK'for e in events))
        pause(.5)
        assert any('DeepSeek执行模式'in e['message']for e in events)
        command('保存点1');command('保存点2');checks.append('validated model save reaches durable place storage')
        command('缺少信息','CLARIFY');command('跳桌','UNSUPPORTED');command('乱输出','INVALID');command('API失败','MODEL_ERROR')
        assert not received and not state['enabled'];checks.append('clarification/unsupported/malformed/API failure never execute')
        command('规定当前地点是点1或者家','CLARIFY');command('保存为','CLARIFY');command('1','CONFIRM_REQUIRED')
        assert json.loads((out/'places.json').read_text())['points']['点1'][:2]==[1.,2.]
        checks.append('two clarification turns retain current-position intent; existing point still requires overwrite confirmation')
        command('确认覆盖点1');assert json.loads((out/'places.json').read_text())['points']['点1'][:2]==[-3.,-4.]
        command('无前文补充','CLARIFY');command('停止','STOPPING');pause(.3)
        command('无前文补充','CLARIFY');command('保存点1','CONFIRM_REQUIRED');command('确认覆盖点1')
        checks.append('stop and completed action clear dialogue context')
        command('去数字一')
        wait(lambda:any('导航总开关当前关闭' in e['message']for e in events));assert not received
        assert '点1' in command('查询1')['message']
        checks.append('digit place/query aliases resolve; disabled gate reports precise reason without enabling')
        command('请开启一下导航');start=len(events);command('帮我先去点1然后回家')
        wait(lambda:any(e['code']=='COMPLETED'for e in events[start:]));assert len(received)==2 and received[0][:2]==[1.,2.] and received[1][:2]==[-3.,-4.]
        checks.append('model route uses existing NavigateTask and sequential success gating')
        command('停止','STOPPING');wait(lambda:not state['enabled']);pause(.3)
        ident=send('text','慢请求');wait(lambda:any(e.get('id')==ident and e['code']=='PARSING'for e in events))
        t=time.monotonic();command('查询状态');assert time.monotonic()-t<.8
        command('立刻停止','STOPPING');pause(1.8);assert not state['enabled']
        checks.append('HTTP worker does not block status/heartbeat; stop invalidates delayed enable')
        ident=send('text','断线慢请求');wait(lambda:any(e.get('id')==ident and e['code']=='PARSING'for e in events))
        send('close',ident='close1');wait(lambda:any(e.get('code')=='STOPPED'for e in events[-5:]));pause(1.8)
        assert not state['enabled'];checks.append('explicit close discards delayed model output')
        send('connect',ident='connect2');pause(.3)
        command('超时请求','MODEL_ERROR');pause(1.5);assert not state['enabled'];checks.append('expired model response cannot execute')
        command('准备覆盖点1','CONFIRM_REQUIRED')
        ident=send('text','慢请求');wait(lambda:any(e.get('id')==ident and e['code']=='PARSING'for e in events))
        command('确认覆盖点1');wait(lambda:any(e.get('id')==ident and e['code']=='STALE_CONTEXT'for e in events));assert not state['enabled']
        checks.append('place changes invalidate model context instead of using stale coordinates')
        command('请开启一下导航');before=len(received)
        ident=send('text','失联慢请求');wait(lambda:any(e.get('id')==ident and e['code']=='PARSING'for e in events))
        state['heartbeats']=False;pause(3.8);assert not state['enabled'] and len(received)==before
        checks.append('heartbeat loss cancels pending model response before it can start navigation')
        state['heartbeats']=True;send('connect',ident='connect3');pause(.4)
        command('代为确认','CONFIRM_REQUIRED');checks.append('model cannot substitute for explicit overwrite confirmation')
        state['duration']=3.;command('请开启一下导航');before=len(received);command('帮我先去点1然后回家')
        wait(lambda:len(received)>before);command('停止','STOPPING');wait(lambda:not state['busy']);pause(.3)
        assert len(received)==before+1;checks.append('local stop cancels active model-generated route and queued home')
        send('close',ident='close2');wait(lambda:any(e.get('code')=='STOPPED'for e in events[-5:]))
        result={'passed':True,'robot_started':False,'rl_started':False,'real_api_called':False,'checks':checks,'goals':received,'out':str(out)}
        (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False),flush=True)
    finally:
        if proc.poll()is None:
            os.killpg(proc.pid,signal.SIGINT)
            try:proc.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=5)
        log.close();server.destroy();n.destroy_node();rclpy.shutdown()


if __name__=='__main__':main()
