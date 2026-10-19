"""Domain214: real lidar clearing -> Smac route refresh -> native MPPI, static odometry. No robot/RL."""
import os,subprocess,signal,time,json,math
from pathlib import Path
import rclpy,yaml,numpy as np
from geometry_msgs.msg import TransformStamped
from lifecycle_msgs.srv import ChangeState
from nav_msgs.msg import OccupancyGrid
from sensor_msgs.msg import PointCloud2
from std_msgs.msg import String
from rclpy.qos import qos_profile_sensor_data,QoSProfile,DurabilityPolicy
from tf2_ros import StaticTransformBroadcaster,TransformBroadcaster
from ament_index_python.packages import get_package_share_directory
assert os.environ.get('ROS_DOMAIN_ID')=='214'
assert os.environ.get('GZ_PARTITION')=='lite3_clearing_20261018'
out=Path(__import__('tempfile').mkdtemp(prefix='lite3-clearing-route-'));root=Path(__file__).resolve().parents[3];procs=[];logs=[]
def spawn(cmd,label):
 f=(out/(label+'.log')).open('w');logs.append(f);p=subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT,start_new_session=True);procs.append(p)
def service(kind,typ,request):
 p=subprocess.run(['gz','service','-s','/world/clearing_fixture/'+kind,'--reqtype',typ,'--reptype','gz.msgs.Boolean','--timeout','4000','--req',request],capture_output=True,text=True,timeout=6)
 assert p.returncode==0 and 'data: true' in p.stdout,p.stdout+p.stderr
sdf=(root/'src/lite3_perception/test/fixtures/clearing_lidar.sdf').read_text().replace('<pose>0 0 .5 0 0 0</pose>','<pose>.3 0 .5 0 0 0</pose>');(out/'world.sdf').write_text(sdf)
# Keep a real visible box as a control. Test box occupies the lidar's upward rays.
for name,x,y,height in [('removed_box',1.5,0.,.65),('retained_box',0.,1.5,.65)]:
 (out/(name+'.sdf')).write_text(f'<sdf version="1.8"><model name="{name}"><static>true</static><pose>{x} {y} {height/2+.005} 0 0 0</pose><link name="l"><collision name="c"><geometry><box><size>.4 1.0 {height}</size></box></geometry></collision><visual name="v"><geometry><box><size>.4 1.0 {height}</size></box></geometry></visual></link></model></sdf>')
configs={}
for name,filename in [('controller','controller_mppi.yaml'),('planner','planner.yaml')]:
 cfg=yaml.safe_load((root/'src/lite3_navigation/config'/filename).read_text());key='local_costmap'if name=='controller'else'global_costmap';cm=cfg[key][key]['ros__parameters'];cm.update(plugins=['static_layer','voxel_layer','inflation_layer'],update_frequency=10.,publish_frequency=10.);cm['voxel_layer']['publish_voxel_map']=False
 # This fixture tests sensor layers, not the motion controller.
 if name=='planner':cfg['planner_server']['ros__parameters']['GridBased']['lattice_filepath']=str(Path(get_package_share_directory('nav2_smac_planner'))/'sample_primitives/5cm_resolution/0.5m_turning_radius/omni/output.json')
 (out/(name+'.yaml')).write_text(yaml.safe_dump(cfg))
rclpy.init();n=rclpy.create_node('clearing_scene_fixture');n.set_parameters([rclpy.parameter.Parameter('use_sim_time',value=True)]);latest={};b=StaticTransformBroadcaster(n)
for parent,child,x,z in [('map','odom',0.,0.),('odom','TORSO',0.,.35),('TORSO','lidar_link',.3,.15)]:
 t=TransformStamped();t.header.frame_id=parent;t.child_frame_id=child;t.transform.translation.x=x;t.transform.translation.z=z;t.transform.rotation.w=1.;b.sendTransform(t)
for topic,kind in [('/global_costmap/costmap',OccupancyGrid),('/local_costmap/costmap',OccupancyGrid),('/lite3/lidar/points',PointCloud2),('/lite3/perception/status',String)]:n.create_subscription(kind,topic,lambda m,k=topic:latest.update({k:m}),qos_profile_sensor_data)
mp=n.create_publisher(OccupancyGrid,'/map',QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL));m=OccupancyGrid();m.header.frame_id='map';m.info.resolution=.05;m.info.width=m.info.height=120;m.info.origin.position.x=m.info.origin.position.y=-3.;m.info.origin.orientation.w=1.;m.data=[0]*14400;m.data[29*120+29]=100;mp.publish(m)
def spin(seconds):
 end=time.monotonic()+seconds
 while time.monotonic()<end:rclpy.spin_once(n,timeout_sec=.02)
def wait(pred,seconds=25):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  rclpy.spin_once(n,timeout_sec=.02)
  if pred():return
 raise AssertionError('timeout '+str(out))
def region(topic,x,y,radius=.24):
 if topic not in latest:return -999
 g=latest[topic];a=[]
 for xx in np.arange(x-radius,x+radius,.025):
  for yy in np.arange(y-radius,y+radius,.025):
   mx=int(math.floor((xx-g.info.origin.position.x)/g.info.resolution));my=int(math.floor((yy-g.info.origin.position.y)/g.info.resolution))
   if 0<=mx<g.info.width and 0<=my<g.info.height:a.append(g.data[my*g.info.width+mx])
 return max(a)if a else-999
from std_srvs.srv import SetBool,Trigger
from nav_msgs.msg import Odometry,Path as RosPath
from lite3_interfaces.action import NavigateTask
from rclpy.action import ActionClient
service_calls={'stops':[],'pauses':[]}
def control(request,response,key):
 service_calls[key].append(request.data);response.success=True;return response
n.create_service(SetBool,'/lite3/set_stop',lambda req,res:control(req,res,'stops'))
n.create_service(SetBool,'/lite3/set_navigation_pause',lambda req,res:control(req,res,'pauses'))
n.create_service(SetBool,'/lite3/set_navigation_mode',lambda req,res:control(req,res,'modes'))
service_calls['modes']=[]
odom=n.create_publisher(Odometry,'/odom',10);dynamic_tf=TransformBroadcaster(n)
def odometry():
 transform=TransformStamped();transform.header.stamp=n.get_clock().now().to_msg();transform.header.frame_id='odom';transform.child_frame_id='base_footprint';transform.transform.rotation.w=1.;dynamic_tf.sendTransform(transform)
 msg=Odometry();msg.header.stamp=n.get_clock().now().to_msg();msg.header.frame_id='odom';msg.child_frame_id='base_footprint';msg.pose.pose.orientation.w=1.;odom.publish(msg)
timer=n.create_timer(.02,odometry)
paths=[];n.create_subscription(RosPath,'/lite3/navigation_path',lambda msg:paths.append(msg) if msg.poses else None, QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL))
def get(future):wait(future.done);return future.result()
def length(path):
 return sum(math.hypot(b.pose.position.x-a.pose.position.x,b.pose.position.y-a.pose.position.y)for a,b in zip(path.poses[:-1],path.poses[1:]))
maps=['/global_costmap/costmap' ,'/local_costmap/costmap'];checks=[];result={'passed':False,'out':str(out),'robot_started':False,'rl_started':False}
try:
 spawn(['gz','sim','-s','-r','--headless-rendering',str(out/'world.sdf')],'gazebo')
 spawn(['ros2','run','ros_gz_bridge','parameter_bridge','/clearing_fixture/lidar/points@sensor_msgs/msg/PointCloud2[gz.msgs.PointCloudPacked','/world/clearing_fixture/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock','--ros-args','-r','/clearing_fixture/lidar/points:=/lite3/lidar/points','-r','/world/clearing_fixture/clock:=/clock'],'bridge')
 spawn(['ros2','run','lite3_perception','pointcloud_obstacles','--ros-args','--params-file',str(Path(get_package_share_directory('lite3_perception'))/'config/flat_ground.yaml'),'-p','forecast_enabled:=false'],'perception')
 for label,pkg,exe in [('controller','nav2_controller','controller_server'),('planner','nav2_planner','planner_server')]:
  spawn(['ros2','run',pkg,exe,'--ros-args','--params-file',str(out/(label+'.yaml'))],label)
  client=n.create_client(ChangeState,'/'+exe+'/change_state');wait(client.service_is_ready)
  for state in [1,3]:
   req=ChangeState.Request();req.transition.id=state;f=client.call_async(req);wait(f.done);assert f.result().success
 wait(lambda:all(region(k,1.5,0.)==0 for k in maps));checks.append('initial free area')
 for name in ['removed_box','retained_box']:service('create','gz.msgs.EntityFactory','sdf_filename: "'+str(out/(name+'.sdf'))+'"')
 wait(lambda:all(region(k,1.5,0.)==100 and region(k,0.,1.5)==100 for k in maps));spin(2);checks.append('both real boxes persist while present')
 spawn(['ros2','run','lite3_navigation','mission_manager','--ros-args','-p','use_sim_time:=true','-p','route_refresh_period:=0.7','-p','stuck_timeout:=15.0'],'mission')
 gate=n.create_client(SetBool,'/lite3/set_navigation_enabled');state=n.create_client(Trigger,'/lite3/get_navigation_state');action=ActionClient(n,NavigateTask,'/navigate_task')
 wait(gate.service_is_ready);assert get(gate.call_async(SetBool.Request(data=True))).success;wait(action.server_is_ready)
 pauses_before=len(service_calls['pauses']);stops_before=len(service_calls['stops'])
 handle=get(action.send_goal_async(NavigateTask.Goal(goal_x=2.4,goal_y=0.,goal_yaw=0.)));assert handle.accepted
 wait(lambda:len(paths)>0);first_length=length(paths[0]);spin(.3)
 service('remove','gz.msgs.Entity','name: "removed_box", type: MODEL');start=time.monotonic()
 wait(lambda:all(region(k,1.5,0.)<99 for k in maps),15)
 result['clear_wall_seconds']=time.monotonic()-start;checks.append('removed tall box cleared in both maps')
 assert all(region(k,0.,1.5)==100 for k in maps);checks.append('retained real box protected')
 assert all(region(k,-1.525,-1.525)==100 for k in maps);checks.append('static map obstacle protected')
 wait(lambda:len(paths)>=2,12)
 new_length=length(paths[-1]);assert first_length-new_length>=.5 and new_length<=first_length*.85,(first_length,new_length)
 assert not handle.get_result_async().done(),'path preemption incorrectly ended navigation'
 assert service_calls['pauses'][pauses_before:]==[] and True not in service_calls['stops'][stops_before:]
 result.update(initial_path_length=first_length,updated_path_length=new_length,route_state=json.loads(get(state.call_async(Trigger.Request())).message))
 assert result['route_state']['route_updates']>=1
 checks.append('cleared box produces shorter Smac route and native controller path update without task pause')
 get(handle.cancel_goal_async());reply=get(handle.get_result_async()).result;assert reply.result_code==NavigateTask.Result.CANCELED
 checks.append('cancel cleans native foreground and background action goals')
 result['passed']=True
finally:
 result['checks']=checks
 if '/lite3/perception/status'in latest:result['perception_status']=json.loads(latest['/lite3/perception/status'].data)
 for topic in maps:
  if topic in latest:np.save(out/(topic.replace('/','_')+'.npy'),np.array(latest[topic].data))
 (out/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
 for p in reversed(procs):
  if p.poll()is None:
   os.killpg(p.pid,signal.SIGINT)
   try:p.wait(timeout=7)
   except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGTERM);p.wait(timeout=5)
 for f in logs:f.close()
 n.destroy_node();rclpy.shutdown()
