#!/usr/bin/env python3
"""Isolated domain222: real warehouse + Smac/costmap; mocked NavigateTask only.
No robot, controller or RL; no real API calls. Tests temporary target generation.
"""
import json,math,os,signal,subprocess,tempfile,time,uuid,sys
from pathlib import Path
import numpy as np
from PIL import Image
import yaml
import rclpy
from rclpy.action import ActionServer,CancelResponse
from rclpy.qos import QoSProfile,DurabilityPolicy
from geometry_msgs.msg import TransformStamped
from lifecycle_msgs.srv import ChangeState
from nav_msgs.msg import OccupancyGrid
from std_msgs.msg import String
from std_srvs.srv import SetBool,Trigger
from tf2_ros import TransformBroadcaster
from lite3_interfaces.action import NavigateTask
from ament_index_python.packages import get_package_share_directory


def main():
    assert os.environ.get('ROS_DOMAIN_ID')=='222'
    assert os.environ.get('GZ_PARTITION')=='lite3_object_approach_20261020'
    root=Path(__file__).resolve().parents[3];out=Path(tempfile.mkdtemp(prefix='lite3-object-approach-'))
    installed=root/'install/lite3_navigation/lib/lite3_navigation';world=root/'install/lite3_gazebo/share/lite3_gazebo/worlds/large_warehouse.sdf';map_file=root/'src/lite3_gazebo/maps/large_warehouse.yaml'
    agent_mode='--agent' in sys.argv
    processes=[];logs=[];events=[];goals=[];checks=[];state={'enabled':False,'pose':[-4.,-4.,0.]}
    rclpy.init();node=rclpy.create_node('object_approach_fixture');tf=TransformBroadcaster(node)
    pub=node.create_publisher(String,'/lite3/interaction/input',50)
    node.create_subscription(String,'/lite3/interaction/events',lambda m:events.append(json.loads(m.data)),100)
    session=str(uuid.uuid4())
    def send(kind,text='',ident=None):
        ident=ident or uuid.uuid4().hex;pub.publish(String(data=json.dumps({'session':session,'kind':kind,'id':ident,'text':text},ensure_ascii=False)));return ident
    def timer():
        send('heartbeat');t=TransformStamped();t.header.frame_id='map';t.child_frame_id='base_footprint';t.header.stamp=node.get_clock().now().to_msg();t.transform.translation.x=state['pose'][0];t.transform.translation.y=state['pose'][1];t.transform.rotation.z=math.sin(state['pose'][2]/2);t.transform.rotation.w=math.cos(state['pose'][2]/2);tf.sendTransform(t)
    node.create_timer(.1,timer)
    def gate(req,rep):state['enabled']=req.data;rep.success=True;rep.message='gate updated';return rep
    def lock(req,rep):rep.success=True;return rep
    def query(req,rep):rep.success=True;rep.message=json.dumps({'navigation_enabled':state['enabled'],'busy':False,'fault_latched':False,'switch_pending':False});return rep
    node.create_service(SetBool,'/lite3/set_navigation_enabled',gate);node.create_service(SetBool,'/lite3/set_stop',lock);node.create_service(Trigger,'/lite3/get_navigation_state',query)
    async def execute(handle):
        goal=[handle.request.goal_x,handle.request.goal_y,handle.request.goal_yaw];goals.append(goal)
        if agent_mode:
            from rclpy.task import Future
            state['pose']=goal;f=Future();start=time.monotonic()
            def ready():
                if not f.done()and time.monotonic()-start>.2:f.set_result(None)
            timer=node.create_timer(.02,ready);await f;node.destroy_timer(timer)
        handle.succeed();result=NavigateTask.Result();result.result_code=0;return result
    server=ActionServer(node,NavigateTask,'/navigate_task',execute_callback=execute,cancel_callback=lambda _:CancelResponse.ACCEPT)
    cfg=yaml.safe_load((root/'src/lite3_navigation/config/planner.yaml').read_text());cp=cfg['planner_server']['ros__parameters'];cm=cfg['global_costmap']['global_costmap']['ros__parameters']
    cp['use_sim_time']=cm['use_sim_time']=False;cm['plugins']=['static_layer','inflation_layer']
    cp['GridBased']['lattice_filepath']=str(Path(get_package_share_directory('nav2_smac_planner'))/'sample_primitives/5cm_resolution/0.5m_turning_radius/omni/output.json')
    params=out/'planner.yaml';params.write_text(yaml.safe_dump(cfg))
    mp=node.create_publisher(OccupancyGrid,'/map',QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL))
    info=yaml.safe_load(map_file.read_text());a=np.array(Image.open(map_file.parent/info['image']))
    m=OccupancyGrid();m.header.frame_id='map';m.info.width=a.shape[1];m.info.height=a.shape[0];m.info.resolution=info['resolution'];m.info.origin.position.x=info['origin'][0];m.info.origin.position.y=info['origin'][1];m.info.origin.orientation.w=1.;m.data=np.where(a[::-1]==0,100,np.where(a[::-1]==205,-1,0)).astype(np.int8).ravel().tolist();mp.publish(m)
    def spawn(cmd,name):
        log=open(out/(name+'.log'),'w');logs.append(log);p=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);processes.append(p);return p
    def kill(p):
        if p.poll()is None:
            os.killpg(p.pid,signal.SIGINT)
            try:p.wait(timeout=8)
            except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
    def wait(pred,seconds=15):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            rclpy.spin_once(node,timeout_sec=.02)
            if pred():return
        raise AssertionError(str(events[-7:])+'\nOUTPUT '+str(out))
    def pause(seconds):
        end=time.monotonic()+seconds;wait(lambda:time.monotonic()>end,seconds+1)
    def command(text,code='OK'):
        ident=send('text',text);wait(lambda:any(e['id']==ident and e['code']not in ('PARSING','INTERPRETED')for e in events))
        rep=next(e for e in reversed(events)if e['id']==ident and e['code']not in ('PARSING','INTERPRETED'))
        assert rep['code']==code,rep;return ident
    try:
        spawn(['gz','sim','-s','-r',str(world)],'gazebo')
        spawn(['ros2','run','nav2_planner','planner_server','--ros-args','--params-file',str(params)],'planner')
        lifecycle=node.create_client(ChangeState,'/planner_server/change_state');wait(lifecycle.service_is_ready)
        for number in (1,3):
            req=ChangeState.Request();req.transition.id=number;f=lifecycle.call_async(req);wait(f.done);assert f.result().success
        args=['--ros-args','-p','world_sdf:='+str(world),'-p','map_yaml:='+str(map_file),'-p','places_file:='+str(out/'places.json'),'-p','environment_file:='+str(out/'semantics.json')]
        backend_cmd=[str(installed/'interaction_backend')]
        if agent_mode:
            stub=out/'native_agent.py'
            stub.write_text('''import sys,json
from importlib.machinery import SourceFileLoader
sys.path.insert(0,sys.argv.pop(1))
b=SourceFileLoader('interaction_backend',sys.path[0]+'/interaction_backend').load_module()
import agent_runtime
counter=0
def tool(name,args):
    global counter
    counter+=1
    return {'role':'assistant','content':'','tool_calls':[{'id':'native_'+str(counter),'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}
def model(messages):
    i=max(i for i,m in enumerate(messages)if m['role']=='user');data=json.loads(messages[i]['content'])
    assert data['request']=='先去东墙，再去货架1，最后回来'
    results=[json.loads(m['content'])for m in messages[i+1:]if m['role']=='tool']
    if not results:return tool('get_environment',{})
    if len(results)==1:
        walls=[r for r in results[0]['objects']if r['category']=='墙体']
        return tool('approach_object',{'object':max(walls,key=lambda r:r['pose_world'][0])['id']})
    assert results[-1]['success']
    if len(results)==2:return tool('approach_object',{'object':'model:shelf_1'})
    if len(results)==3:return tool('return_to_start',{})
    return {'role':'assistant','content':'东墙、货架1和返回出发处均完成。'}
agent_runtime.request_turn=model
b.main()
''')
            backend_cmd=['/usr/bin/python3',str(stub),str(installed)]
            args+=['-p','language_mode:=deepseek','-p','agent_tools:=true']
        spawn(backend_cmd+args,'backend')
        for _ in range(30):
            ident=send('connect');pause(.2)
            if any(e['id']==ident and e['code']=='OK'for e in events):break
        wait(lambda:any(e['code']=='OK'for e in events));pause(2)
        if agent_mode:
            command('开启导航');ident=send('text','先去东墙，再去货架1，最后回来')
            wait(lambda:any(e['id']==ident and e['code']=='OK'for e in events),90)
            reply=next(e for e in reversed(events)if e['id']==ident and e['code']=='OK')
            assert len(goals)==3 and math.dist(goals[-1][:2],[-4.,-4.])<.01
            assert [r['tool']for r in reply['tool_results']]==['get_environment','approach_object','approach_object','return_to_start']
            assert not(out/'places.json').exists()
            checks.append('native tool loop uses real Gazebo scene/poses and Smac/full-footprint costmap for east wall then shelf1')
            checks.append('mocked task success updates TF; subsequent native planning starts at actual previous endpoint; final returns to initial pose')
            checks.append('temporary multi-object targets are not persisted; no real API/robot/RL')
        else:
            command('标注物体 shelf_1 名称=货架A 类别=货架 别名=一号货架')
            before=len(goals);ident=command('去货架A旁边')
            wait(lambda:any(e['id']==ident and e['code']=='REJECTED'for e in events));assert len(goals)==before and not state['enabled']
            checks.append('disabled navigation rejects approach without unlocking or issuing NavigateTask')
            command('开启导航');start=len(events);ident=command('去货架A旁边')
            wait(lambda:any(e['code']=='COMPLETED'for e in events[start:]),40)
            ready=next(e for e in events[start:]if e['code']=='APPROACH_READY');target=ready['temporary_target']
            assert len(goals)==before+1 and math.dist(goals[-1][:2],target[:2])<1e-6
            assert not (out/'places.json').exists() and len(json.loads((out/'semantics.json').read_text())['annotations'])==1
            checks.append('real Smac/full-footprint costmap selects reachable temporary pose, then existing NavigateTask receives it')
            checks.append('temporary targets are not written to Places or semantic annotations')
            start=len(events);command('去一号货架南侧 距离=0.5')
            wait(lambda:any(e['code']=='COMPLETED'for e in events[start:]),40)
            ready=next(e for e in events[start:]if e['code']=='APPROACH_READY')
            assert ready['temporary_target'][1]<2.5934 and abs((ready['temporary_target'][2]-90+180)%360-180)<2
            checks.append('world-south approach honors explicit body-edge clearance and faces shelf')
        send('close');pause(.4)
        result={'passed':True,'agent_tools':agent_mode,'checks':checks,'targets':goals,'real_planner':True,'synthetic_map_publisher':True,'sensor_layers_enabled':False,'mocked_navigate_task':True,'robot_started':False,'rl_started':False,'real_api_called':False,'out':str(out)}
        (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False),flush=True)
    finally:
        for p in reversed(processes):kill(p)
        for log in logs:log.close()
        server.destroy();node.destroy_node();rclpy.shutdown()

if __name__=='__main__':main()
