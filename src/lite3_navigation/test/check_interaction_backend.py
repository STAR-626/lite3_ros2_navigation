#!/usr/bin/env python3
"""Domain218: real interaction backend, mocked existing task/gate interfaces; no robot/RL."""
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
    assert os.environ.get('ROS_DOMAIN_ID')=='218'
    root=Path(__file__).resolve().parents[3];out=Path(tempfile.mkdtemp(prefix='lite3-interaction-'))
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
    log=(out/'backend.log').open('w');proc=subprocess.Popen(['ros2','run','lite3_navigation','interaction_backend','--ros-args','-p','map_yaml:='+str(root/'src/lite3_gazebo/maps/large_warehouse.yaml'),'-p','places_file:='+str(out/'places.json')],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    checks=[]
    def wait(pred,seconds=8):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            rclpy.spin_once(n,timeout_sec=.02)
            if pred():return
        raise AssertionError((out/'backend.log').read_text()[-3000:]+'\nevents:'+str(events[-8:]))
    def command(text,code='OK'):
        ident=send('text',text);wait(lambda:any(e.get('id')==ident for e in events));reply=next(e for e in reversed(events)if e.get('id')==ident)
        assert reply['code']==code,reply;return reply
    def pause(seconds):
        start=time.monotonic();wait(lambda:time.monotonic()-start>seconds,seconds+1)
    try:
        for _ in range(15):
            send('connect',ident='connect');pause(.2)
            if any(e['id']=='connect' and e['code']=='OK'for e in events):break
        wait(lambda:any(e['id']=='connect' and e['code']=='OK'for e in events))
        pause(.5)
        command('把坐标1、2，朝向90度设成点1');command('把当前位置设成点2')
        assert json.loads((out/'places.json').read_text())['points']['点2']==[-3.,-4.,0.];checks.append('named/current places persist; home uses current TF')
        command('把坐标2、3设成点1','CONFIRM_REQUIRED');assert json.loads((out/'places.json').read_text())['points']['点1'][0]==1
        command('确认覆盖点1');checks.append('overwrite requires explicit matching confirmation')
        before=len(received);command('先去点1，再去不存在','INVALID');pause(.3);assert len(received)==before;checks.append('missing place rejects whole route before motion')
        command('开启导航');start=len(events);command('先去点1，再去点2，然后回到原点')
        wait(lambda:any(e['code']=='COMPLETED'for e in events[start:]))
        assert len(received)==3 and received[0][:2]==[2.,3.] and received[1][:2]==[-3.,-4.] and received[2][:2]==[-3.,-4.] and state['max_active']==1
        checks.append('three NavigateTask goals execute sequentially after successful result')
        state['fail']=True;start=len(received);command('先去点1，再去点2');wait(lambda:not state['enabled']);pause(.4);assert len(received)==start+1;checks.append('failed first leg cancels remaining route and closes navigation')
        state['fail']=False;state['duration']=4.;command('开启导航');start=len(received);command('先去点1，再去点2');wait(lambda:len(received)>start)
        command('查询状态');command('停止','STOPPING');wait(lambda:not state['enabled']);pause(.4);assert len(received)==start+1;checks.append('status works while busy; stop clears queued goals')
        wait(lambda:not state['busy']);command('开启导航');start=len(received);command('先去点1，再去点2');wait(lambda:len(received)>start)
        state['heartbeats']=False;wait(lambda:not state['enabled'],5);pause(.4);assert len(received)==start+1;checks.append('lost heartbeat cancels active and queued work')
        wait(lambda:not state['busy']);send('connect',ident='connect2');state['heartbeats']=True;pause(.4)
        state['duration']=.3;command('开启导航');start=len(received);start_events=len(events)
        ident=uuid.uuid4().hex;send('text','去点1',ident);send('text','去点1',ident)
        wait(lambda:any(e['code']=='COMPLETED'for e in events[start_events:]));assert len(received)==start+1
        checks.append('duplicate request id cannot start a second task')
        state['accept_delay']=1.;command('开启导航');start=len(received)
        command('先去点1，再去点2');wait(lambda:state['accept_waiting'])
        command('停止','STOPPING');wait(lambda:not state['accept_waiting']);pause(.6)
        assert not state['enabled'] and len(received)<=start+1 and not state['busy']
        checks.append('stop during delayed goal acceptance cancels late handle and prevents next leg')
        state['accept_delay']=0.
        command('点1在哪里');command('删除点1');assert '点1'not in json.loads((out/'places.json').read_text())['points'];checks.append('session reconnect and place deletion')
        send('close',ident='close');wait(lambda:any(e['code']=='STOPPED'for e in events[-5:]));checks.append('explicit close confirms stop')
        state['heartbeats']=False
        console_log=(out/'console.log').open('w')
        console=subprocess.Popen(['ros2','run','lite3_navigation','ai_console'],stdin=subprocess.PIPE,stdout=console_log,stderr=subprocess.STDOUT,text=True)
        try:
            wait(lambda:'已连接' in (out/'console.log').read_text())
            console.stdin.write('帮助\n');console.stdin.flush()
            wait(lambda:'支持：' in (out/'console.log').read_text())
            console.stdin.write('退出\n');console.stdin.flush();wait(lambda:console.poll()is not None)
            assert console.returncode==0
            assert '停止已由任务节点确认' in (out/'console.log').read_text()
            checks.append('installed ai_console accepts terminal input and exits after stop acknowledgment')
        finally:
            if console.poll()is None:console.terminate();console.wait(timeout=5)
            console_log.close()
        interrupted_log=(out/'console_sigint.log').open('w')
        console=subprocess.Popen(['/usr/bin/python3',str(root/'install/lite3_navigation/lib/lite3_navigation/ai_console')],stdin=subprocess.PIPE,stdout=interrupted_log,stderr=subprocess.STDOUT,text=True)
        try:
            wait(lambda:'已连接' in (out/'console_sigint.log').read_text())
            os.kill(console.pid,signal.SIGINT)
            wait(lambda:console.poll()is not None)
            assert console.returncode==0
            assert '停止已由任务节点确认' in (out/'console_sigint.log').read_text()
            checks.append('Ctrl+C keeps ROS context alive until explicit stop acknowledgment')
        finally:
            if console.poll()is None:console.terminate();console.wait(timeout=5)
            interrupted_log.close()
        result={'passed':True,'robot_started':False,'rl_started':False,'checks':checks,'goals':received,'out':str(out)}
        (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False),flush=True)
    finally:
        if proc.poll()is None:
            os.killpg(proc.pid,signal.SIGINT)
            try:proc.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=5)
        log.close();server.destroy();n.destroy_node();rclpy.shutdown()


if __name__=='__main__':main()
