#!/usr/bin/env python3
"""Domain224: native-tool loop, real installed backend, mocked Nav2/scene/API.
No keys/network/robot/Gazebo. Proves serial result gating and interruption.
"""
import json,math,os,signal,subprocess,tempfile,time,uuid,xml.etree.ElementTree as ET
from pathlib import Path
import rclpy
from rclpy.action import ActionServer,CancelResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.task import Future
from geometry_msgs.msg import TransformStamped,PoseStamped
from nav2_msgs.action import ComputePathToPose
from nav2_msgs.srv import GetCostmap
from rcl_interfaces.msg import ParameterValue
from rcl_interfaces.srv import GetParameters
from std_msgs.msg import String
from std_srvs.srv import SetBool,Trigger
from tf2_ros import TransformBroadcaster
from lite3_interfaces.action import NavigateTask


def main():
    assert os.environ.get('ROS_DOMAIN_ID')=='224'
    root=Path(__file__).resolve().parents[3];out=Path(tempfile.mkdtemp(prefix='lite3-agent-tools-'));installed=root/'install/lite3_navigation/lib/lite3_navigation'
    world=root/'src/lite3_gazebo/worlds/large_warehouse.sdf';scene_file=out/'scene.json';objects=[]
    for index,m in enumerate(ET.parse(world).getroot().find('world').findall('model')):
        if m.get('name').startswith(('shelf_','wall_')):
            p=list(map(float,m.findtext('pose').split()));objects.append({'name':m.get('name'),'entity_id':index+10,'pose':[p[0],p[1],p[2],math.degrees(p[5])],'level':True})
    scene_file.write_text(json.dumps({'ok':True,'world':'large_warehouse','models':objects}))
    rclpy.init();n=rclpy.create_node('agent_fixture');tf=TransformBroadcaster(n);group=ReentrantCallbackGroup()
    events=[];goals=[];checks=[];state={'enabled':False,'busy':False,'pose':[-4.,-4.,0.],'fail':False,'duration':.2,'heartbeats':True}
    session=str(uuid.uuid4());pub=n.create_publisher(String,'/lite3/interaction/input',50)
    n.create_subscription(String,'/lite3/interaction/events',lambda m:events.append(json.loads(m.data)),200)
    def send(kind,text='',ident=None):
        ident=ident or uuid.uuid4().hex;pub.publish(String(data=json.dumps({'session':session,'id':ident,'kind':kind,'text':text},ensure_ascii=False)));return ident
    def tick():
        if state['heartbeats']:send('heartbeat')
        p=state['pose'];t=TransformStamped();t.header.frame_id='map';t.child_frame_id='base_footprint';t.header.stamp=n.get_clock().now().to_msg();t.transform.translation.x=p[0];t.transform.translation.y=p[1];t.transform.rotation.z=math.sin(p[2]/2);t.transform.rotation.w=math.cos(p[2]/2);tf.sendTransform(t)
    n.create_timer(.05,tick)
    def gate(req,rep):state['enabled']=req.data;rep.success=True;rep.message='navigation '+str(req.data);return rep
    def lock(req,rep):rep.success=True;return rep
    def status(req,rep):rep.success=True;rep.message=json.dumps({'navigation_enabled':state['enabled'],'busy':state['busy'],'fault_latched':False,'switch_pending':False});return rep
    n.create_service(SetBool,'/lite3/set_navigation_enabled',gate);n.create_service(SetBool,'/lite3/set_stop',lock);n.create_service(Trigger,'/lite3/get_navigation_state',status)
    def footprint(req,rep):rep.values=[ParameterValue(type=4,string_value='[[0.4,0.18],[-0.4,0.18],[-0.4,-0.18],[0.4,-0.18]]'),ParameterValue(type=3,double_value=.07),ParameterValue(type=4,string_value='map')];return rep
    def profile(req,rep):rep.values=[ParameterValue(type=4,string_value='nav2_smac_planner::SmacPlannerLattice')];return rep
    def grid(req,rep):
        m=rep.map;m.header.frame_id='map';m.metadata.update_time=n.get_clock().now().to_msg();m.metadata.resolution=.05;m.metadata.size_x=m.metadata.size_y=240;m.metadata.origin.position.x=m.metadata.origin.position.y=-6.;m.metadata.origin.orientation.w=1.;m.data=[0]*57600;return rep
    n.create_service(GetParameters,'/global_costmap/global_costmap/get_parameters',footprint);n.create_service(GetParameters,'/planner_server/get_parameters',profile);n.create_service(GetCostmap,'/global_costmap/get_costmap',grid)
    async def delay(seconds,predicate=lambda:False):
        f=Future();started=time.monotonic()
        def ready():
            if not f.done()and(time.monotonic()-started>seconds or predicate()):f.set_result(None)
        timer=n.create_timer(.02,ready);await f;n.destroy_timer(timer)
    def plan(handle):
        handle.succeed();result=ComputePathToPose.Result();result.error_code=0;result.path.header.frame_id='map'
        p=state['pose'];start=PoseStamped();start.header.frame_id='map';start.pose.position.x=p[0];start.pose.position.y=p[1];start.pose.orientation.z=math.sin(p[2]/2);start.pose.orientation.w=math.cos(p[2]/2)
        result.path.poses=[start,handle.request.goal];return result
    async def navigate(handle):
        goal=[handle.request.goal_x,handle.request.goal_y,handle.request.goal_yaw];goals.append(goal);state['busy']=True;fail=state['fail']
        await delay(state['duration'],lambda:handle.is_cancel_requested or not state['enabled']);state['busy']=False;result=NavigateTask.Result()
        if handle.is_cancel_requested:handle.canceled();result.result_code=7
        elif not state['enabled']:handle.abort();result.result_code=7
        elif fail:handle.abort();result.result_code=2;result.message='test blocked'
        else:
            state['pose']=goal;await delay(.15);handle.succeed();result.result_code=0
        return result
    planner=ActionServer(n,ComputePathToPose,'/compute_path_to_pose',execute_callback=plan)
    task=ActionServer(n,NavigateTask,'/navigate_task',execute_callback=navigate,cancel_callback=lambda _:CancelResponse.ACCEPT,callback_group=group)
    stub=out/'stub.py';stub.write_text('''import sys,json,time
from pathlib import Path
from importlib.machinery import SourceFileLoader
sys.path.insert(0,sys.argv.pop(1));scene_file=sys.argv.pop(1)
b=SourceFileLoader('interaction_backend',sys.path[0]+'/interaction_backend').load_module()
import agent_runtime
class Reader:
    def __init__(self,*a):pass
    def snapshot(self):return json.loads(Path(scene_file).read_text())
    def close(self):pass
b.EnvironmentReader=Reader
counter=0
def calls(items):
    global counter
    cs=[]
    for name,args in items:
        counter+=1;cs.append({'id':'native_'+str(counter),'type':'function','function':{'name':name,'arguments':json.dumps(args,ensure_ascii=False)}})
    return {'role':'assistant','content':'','tool_calls':cs}
def final(text):return {'role':'assistant','content':text}
def model(messages):
    users=[i for i,m in enumerate(messages)if m['role']=='user'];i=users[-1];data=json.loads(messages[i]['content']);text=data['request'];turn=messages[i+1:];results=[json.loads(m['content'])for m in turn if m['role']=='tool']
    assert data['environment']['axes']=={'east':'+X','north':'+Y'}
    assert text not in ('先去','东墙')
    if text=='先去东墙，再去货架1，最后回来':
        if not results:return calls([('get_environment',{})])
        objects=results[0]['objects'];walls=[r for r in objects if r['category']=='墙体'];east=max(walls,key=lambda r:r['pose_world'][0])
        if len(results)==1:return calls([('approach_object',{'object':east['id']})])
        if len(results)==2:
            assert results[-1]['success'] and 'final_pose'in results[-1]
            return calls([('approach_object',{'object':'model:shelf_1'})])
        if len(results)==3:
            assert results[-1]['success'];return calls([('return_to_start',{})])
        assert results[-1]['success'];return final('东墙和货架1已到达，并返回本轮出发处。')
    if text=='再去第二个':
        assert any('先去东墙' in m.get('content','')for m in messages[:i])
        if not results:return calls([('get_object',{'object':'model:shelf_1'})])
        if len(results)==1:return calls([('approach_object',{'object':'model:shelf_1'})])
        return final('已再次到达刚才第二个对象货架1旁。')
    if text=='创建测试地点':
        if not results:return calls([('save_place',{'name':'点1','pose':[1,2,0]}),('save_place',{'name':'点2','pose':[2,3,0]})])
        return final('两个测试地点已保存。')
    if text=='把这些点都删了':
        if not results:return calls([('list_places',{})])
        if len(results)==1:
            assert len(results[0]['places'])==2;return calls([('delete_places',{'all':True})])
        return final('已删除全部已保存地点。')
    if text=='慢网络':time.sleep(1.5);return calls([('approach_object',{'object':'model:shelf_1'})])
    if text in ('去两处测试取消','去两处测试失败'):
        if not results:return calls([('approach_object',{'object':'model:shelf_1'}),('approach_object',{'object':'model:shelf_2'})])
        if text.endswith('失败'):
            assert len(results)==2 and not results[0]['success']and not results[1]['success']
            return final('第一步受阻，第二步未执行，导航已关闭。')
        return final('已完成。')
    if text=='未知工具':return calls([('list_places',{}),('exec',{'cmd':'rm project'})])
    if text=='断线网络':time.sleep(3.2);return calls([('approach_object',{'object':'model:shelf_1'})])
    raise ValueError('no mock case')
agent_runtime.request_turn=model
b.main()
''')
    log=open(out/'backend.log','w');proc=subprocess.Popen(['/usr/bin/python3',str(stub),str(installed),str(scene_file),'--ros-args','-p','language_mode:=deepseek','-p','agent_tools:=true','-p','world_sdf:='+str(world),'-p','map_yaml:='+str(root/'src/lite3_gazebo/maps/large_warehouse.yaml'),'-p','places_file:='+str(out/'places.json'),'-p','environment_file:='+str(out/'semantics.json')],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    def wait(pred,seconds=15):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            rclpy.spin_once(n,timeout_sec=.02)
            if pred():return
        raise AssertionError(str(events[-10:])+'\n'+(out/'backend.log').read_text()[-3000:])
    def pause(seconds):
        end=time.monotonic()+seconds;wait(lambda:time.monotonic()>end,seconds+1)
    def terminal(text,code='OK'):
        ident=send('text',text);wait(lambda:any(e['id']==ident and e['code']==code for e in events));return ident
    def agent(text,code='OK'):
        ident=send('text',text);wait(lambda:any(e['id']==ident and e['code']==code for e in events),40);return next(e for e in reversed(events)if e['id']==ident and e['code']==code)
    try:
        for _ in range(30):
            ident=send('connect');pause(.15)
            if any(e['id']==ident and e['code']=='OK'for e in events):break
        wait(lambda:any(e['code']=='OK'for e in events));pause(.3);terminal('开启导航')
        rep=agent('先去东墙，再去货架1，最后回来');assert len(goals)==3 and math.dist(goals[-1][:2],[-4.,-4.])<.01
        motion=[r for r in rep['tool_results']if r['tool']in ('approach_object','return_to_start')]
        assert [r['arguments'].get('object')for r in motion[:2]]==['model:wall_east','model:shelf_1'] and all(r['result']['success']for r in motion)
        checks.append('complete original sentence + spatial directory passed; environment query→east wall→shelf1→task-start, actual results gate each step')
        agent('再去第二个');assert len(goals)==4;checks.append('completed tool history supports subsequent reference to previous second object')
        agent('创建测试地点');assert len(json.loads((out/'places.json').read_text())['points'])==2
        agent('把这些点都删了');assert json.loads((out/'places.json').read_text())['points']=={};checks.append('model queries actual places then atomically deletes all; home and object directory retained')
        before=len(goals);ident=send('text','慢网络');wait(lambda:any(e['id']==ident and e['code']=='PARSING'for e in events))
        started=time.monotonic();terminal('查询状态');assert time.monotonic()-started<.8
        terminal('停止','STOPPING');pause(1.8);assert len(goals)==before and not state['enabled'];checks.append('status/stop remain local during HTTP; delayed tool response cannot move robot')
        terminal('开启导航');state['duration']=2.;before=len(goals);ident=send('text','去两处测试取消');wait(lambda:len(goals)>before)
        terminal('停止','STOPPING');pause(.5);assert len(goals)==before+1 and not state['enabled'];checks.append('stop cancels active leg and prevents queued second object')
        terminal('开启导航');state['duration']=.1;state['fail']=True;before=len(goals)
        rep=agent('去两处测试失败');assert len(goals)==before+1 and not state['enabled']
        assert len(rep['tool_results'])==2 and all(not r['result']['success']for r in rep['tool_results']);state['fail']=False
        checks.append('failed action fed to model after stop cleanup; queued motion blocked even when model requested it')
        before=len(goals);rep=agent('未知工具','MODEL_ERROR');assert len(goals)==before;checks.append('whole tool batch validated; unsupported shell tool never executes')
        terminal('开启导航');ident=send('text','断线网络');wait(lambda:any(e['id']==ident and e['code']=='PARSING'for e in events));state['heartbeats']=False;pause(3.6)
        assert len(goals)==before and not state['enabled'];checks.append('heartbeat loss invalidates delayed native tool response and closes navigation')
        result={'passed':True,'checks':checks,'goals':goals,'real_api_called':False,'robot_started':False,'rl_started':False,'out':str(out)}
        (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False),flush=True)
    finally:
        if proc.poll()is None:
            os.killpg(proc.pid,signal.SIGINT)
            try:proc.wait(timeout=7)
            except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
        log.close();planner.destroy();task.destroy();n.destroy_node();rclpy.shutdown()

if __name__=='__main__':main()
