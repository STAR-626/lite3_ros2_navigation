#!/usr/bin/env python3
"""Domain223: installed backend with mock scene/Nav2/model; no robot/API/Gazebo.
Exercises stop/late acceptance, map rejection, object movement and temporary data.
"""
import json,math,os,signal,subprocess,tempfile,time,uuid
from pathlib import Path
import rclpy
from rclpy.action import ActionServer,CancelResponse,GoalResponse
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
    assert os.environ.get('ROS_DOMAIN_ID')=='223'
    root=Path(__file__).resolve().parents[3];out=Path(tempfile.mkdtemp(prefix='lite3-approach-protocol-'));installed=root/'install/lite3_navigation/lib/lite3_navigation'
    scene_file=out/'scene.json';model={'name':'shelf_1','entity_id':42,'pose':[0.,0.,.03,0.],'level':True}
    def scene(m):scene_file.write_text(json.dumps({'ok':True,'world':'large_warehouse','models':[m]}))
    scene(model)
    rclpy.init();n=rclpy.create_node('approach_fixture');group=ReentrantCallbackGroup();tf=TransformBroadcaster(n)
    events=[];plans=[];goals=[];checks=[];state={'enabled':False,'busy':False,'blocked':False,'duration':.1,'accept_delay':0.,'accept_waiting':False,'fail_first':False,'bad_end':False,'task_delay':.1,'heartbeats':True,'stale_map':False}
    session=str(uuid.uuid4());pub=n.create_publisher(String,'/lite3/interaction/input',50)
    n.create_subscription(String,'/lite3/interaction/events',lambda m:events.append(json.loads(m.data)),150)
    def send(kind,text='',ident=None):
        ident=ident or uuid.uuid4().hex;pub.publish(String(data=json.dumps({'session':session,'id':ident,'kind':kind,'text':text},ensure_ascii=False)));return ident
    def timer():
        if state['heartbeats']:send('heartbeat')
        t=TransformStamped();t.header.frame_id='map';t.child_frame_id='base_footprint';t.header.stamp=n.get_clock().now().to_msg();t.transform.translation.x=-4.;t.transform.translation.y=-4.;t.transform.rotation.w=1.;tf.sendTransform(t)
    n.create_timer(.1,timer)
    def gate(req,rep):state['enabled']=req.data;rep.success=True;rep.message='gate';return rep
    def lock(req,rep):rep.success=True;return rep
    def status(req,rep):rep.success=True;rep.message=json.dumps({'navigation_enabled':state['enabled'],'busy':state['busy'],'fault_latched':False,'switch_pending':False});return rep
    n.create_service(SetBool,'/lite3/set_navigation_enabled',gate);n.create_service(SetBool,'/lite3/set_stop',lock);n.create_service(Trigger,'/lite3/get_navigation_state',status)
    def footprint(req,rep):rep.values=[ParameterValue(type=4,string_value='[[0.4,0.18],[-0.4,0.18],[-0.4,-0.18],[0.4,-0.18]]'),ParameterValue(type=3,double_value=.07),ParameterValue(type=4,string_value='map')];return rep
    def profile(req,rep):rep.values=[ParameterValue(type=4,string_value='nav2_smac_planner::SmacPlannerLattice')];return rep
    def grid(req,rep):
        m=rep.map;m.header.frame_id='map';m.metadata.update_time=n.get_clock().now().to_msg()
        if state['stale_map']:m.metadata.update_time.sec-=10
        m.metadata.resolution=.05;m.metadata.size_x=m.metadata.size_y=200;m.metadata.origin.position.x=m.metadata.origin.position.y=-5.;m.metadata.origin.orientation.w=1.;m.data=[255 if state['blocked']else 0]*40000;return rep
    n.create_service(GetParameters,'/global_costmap/global_costmap/get_parameters',footprint)
    n.create_service(GetParameters,'/planner_server/get_parameters',profile)
    n.create_service(GetCostmap,'/global_costmap/get_costmap',grid)
    async def delay(seconds,condition=lambda:False):
        f=Future();start=time.monotonic()
        def check():
            if not f.done()and(time.monotonic()-start>seconds or condition()):f.set_result(None)
        timer=n.create_timer(.02,check);await f;n.destroy_timer(timer)
    async def accept(req):
        state['accept_waiting']=True;await delay(state['accept_delay']);state['accept_waiting']=False;return GoalResponse.ACCEPT
    async def plan(handle):
        plans.append(handle.request.goal);await delay(state['duration'],lambda:handle.is_cancel_requested)
        result=ComputePathToPose.Result()
        if handle.is_cancel_requested:handle.canceled();result.error_code=200
        elif state['fail_first']:
            state['fail_first']=False;handle.abort();result.error_code=208
        else:
            handle.succeed();result.error_code=0;result.path.header.frame_id='map'
            start=PoseStamped();start.header.frame_id='map';start.pose.position.x=-4.;start.pose.position.y=-4.;start.pose.orientation.w=1.
            result.path.poses=[start,handle.request.goal]
            if state['bad_end']:result.path.poses[-1].pose.position.x+=1.
        return result
    async def navigate(handle):
        goals.append([handle.request.goal_x,handle.request.goal_y,handle.request.goal_yaw]);state['busy']=True
        await delay(state['task_delay'],lambda:handle.is_cancel_requested or not state['enabled']);state['busy']=False
        result=NavigateTask.Result()
        if handle.is_cancel_requested:handle.canceled();result.result_code=7
        elif not state['enabled']:handle.abort();result.result_code=7
        else:handle.succeed();result.result_code=0
        return result
    planner=ActionServer(n,ComputePathToPose,'/compute_path_to_pose',execute_callback=plan,goal_callback=accept,cancel_callback=lambda _:CancelResponse.ACCEPT,callback_group=group)
    task=ActionServer(n,NavigateTask,'/navigate_task',execute_callback=navigate,cancel_callback=lambda _:CancelResponse.ACCEPT,callback_group=group)
    stub=out/'stub.py';stub.write_text('''import sys,json
from pathlib import Path
from importlib.machinery import SourceFileLoader
sys.path.insert(0,sys.argv.pop(1));scene_file=sys.argv.pop(1)
b=SourceFileLoader('interaction_backend',sys.path[0]+'/interaction_backend').load_module()
class Reader:
    def __init__(self,*args):pass
    def snapshot(self):return json.loads(Path(scene_file).read_text())
    def close(self):pass
b.EnvironmentReader=Reader
def model(text,names,history=None,environment=None):
    if text=='开启导航':return {'action':'enable'}
    assert any(r['name']=='货架A'for r in environment['objects'])
    return {'action':'approach','object':'model:shelf_1'}
b.interpret=model
b.main()
''')
    log=open(out/'backend.log','w');p=subprocess.Popen(['/usr/bin/python3',str(stub),str(installed),str(scene_file),'--ros-args','-p','language_mode:=deepseek','-p','world_sdf:='+str(root/'src/lite3_gazebo/worlds/large_warehouse.sdf'),'-p','map_yaml:='+str(root/'src/lite3_gazebo/maps/large_warehouse.yaml'),'-p','places_file:='+str(out/'places.json'),'-p','environment_file:='+str(out/'semantics.json')],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    def wait(pred,seconds=12):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            rclpy.spin_once(n,timeout_sec=.02)
            if pred():return
        raise AssertionError(str(events[-8:])+'\n'+(out/'backend.log').read_text()[-2000:])
    def pause(seconds):
        end=time.monotonic()+seconds;wait(lambda:time.monotonic()>end,seconds+1)
    def command(text,code='OK'):
        ident=send('text',text);wait(lambda:any(e['id']==ident and e['code']not in ('PARSING','INTERPRETED')for e in events));rep=next(e for e in reversed(events)if e['id']==ident and e['code']not in ('PARSING','INTERPRETED'));assert rep['code']==code,rep;return ident
    def rejected(ident):wait(lambda:any(e['id']==ident and e['code']=='REJECTED'for e in events))
    def enable():command('开启导航');wait(lambda:state['enabled'])
    try:
        for _ in range(30):
            ident=send('connect');pause(.15)
            if any(e['id']==ident and e['code']=='OK'for e in events):break
        wait(lambda:any(e['code']=='OK'for e in events));pause(.3)
        command('标注物体 shelf_1 名称=货架A 别名=一号货架')
        rejected(command('去货架A旁边'));assert not plans and not goals;checks.append('closed gate: no planner/navigation goal and no implicit unlock')
        enable();state['blocked']=True;rejected(command('去货架A旁边'));assert not plans and not goals;state['blocked']=False
        checks.append('unknown/full blocked grid: no candidate accepted or navigation started')
        state['stale_map']=True;rejected(command('去货架A旁边'));assert not goals;state['stale_map']=False
        checks.append('stale costmap rejected')
        state['fail_first']=True;before=len(plans);start=len(events);command('请帮我靠近一号货架')
        wait(lambda:any(e['code']=='COMPLETED'for e in events[start:]));assert len(plans)==before+2 and len(goals)==1
        assert not(out/'places.json').exists();checks.append('validated model approach + first unreachable candidate fallback; target not persisted')
        state['duration']=1.5;before=len(goals);count=len(plans);command('去货架A旁边');wait(lambda:len(plans)>count)
        command('停止','STOPPING');pause(1.8);assert len(goals)==before and not state['enabled'];checks.append('stop during planning discards result and cancels planner without movement')
        state['duration']=.1;state['accept_delay']=1.3;enable();command('去货架A旁边');wait(lambda:state['accept_waiting'])
        command('停止','STOPPING');pause(1.6);assert len(goals)==before and not state['enabled'];state['accept_delay']=0.
        checks.append('stop before late planner acceptance cancels accepted handle; no mission dispatch')
        enable();state['duration']=1.;count=len(plans);ident=command('去货架A旁边');wait(lambda:len(plans)>count)
        scene({**model,'pose':[1.,0.,.03,0.]});rejected(ident);assert len(goals)==before;scene(model)
        checks.append('object moved during planning invalidates temporary target')
        state['duration']=.1;state['bad_end']=True;rejected(command('去货架A旁边'));assert len(goals)==before;state['bad_end']=False
        checks.append('planner endpoint mismatch rejected')
        state['duration']=7.;ident=command('去货架A旁边');rejected(ident);pause(.3);assert len(goals)==before
        state['duration']=.1;checks.append('planner timeout: late result cannot dispatch mission')
        state['task_delay']=3.;start=len(events);command('去货架A旁边');wait(lambda:len(goals)>before)
        scene({**model,'pose':[1.,0.,.03,0.]});wait(lambda:not state['enabled']);wait(lambda:not state['busy']);scene(model);pause(.3)
        assert not any(e['code']=='COMPLETED'for e in events[start:]);checks.append('object moved during navigation cancels existing task and closes gate')
        enable();state['duration']=3.;before=len(goals);count=len(plans);command('去货架A旁边');wait(lambda:len(plans)>count)
        state['heartbeats']=False;pause(3.1);assert not state['enabled']and len(goals)==before
        checks.append('console heartbeat loss cancels approach preflight and late dispatch')
        result={'passed':True,'checks':checks,'planned_candidates':len(plans),'mission_targets':goals,'real_api_called':False,'robot_started':False,'rl_started':False,'out':str(out)}
        (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False),flush=True)
    finally:
        if p.poll()is None:
            os.killpg(p.pid,signal.SIGINT)
            try:p.wait(timeout=6)
            except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
        log.close();planner.destroy();task.destroy();n.destroy_node();rclpy.shutdown()

if __name__=='__main__':main()
