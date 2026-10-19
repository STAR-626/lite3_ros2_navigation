"""Real Gazebo lidar + perception + two native costmaps; no robot, RL or motion."""
import os,subprocess,signal,time,json,math
from pathlib import Path
import rclpy,yaml,numpy as np
from geometry_msgs.msg import TransformStamped
from lifecycle_msgs.srv import ChangeState
from nav_msgs.msg import OccupancyGrid
from sensor_msgs.msg import PointCloud2
from std_msgs.msg import String
from rclpy.qos import qos_profile_sensor_data,QoSProfile,DurabilityPolicy
from tf2_ros import StaticTransformBroadcaster
from ament_index_python.packages import get_package_share_directory
assert os.environ.get('ROS_DOMAIN_ID')=='214'
assert os.environ.get('GZ_PARTITION')=='lite3_clearing_20261018'
out=Path(__import__('tempfile').mkdtemp(prefix='lite3-clearing-scene-'));root=Path(__file__).resolve().parents[3];procs=[];logs=[]
def spawn(cmd,label):
 f=(out/(label+'.log')).open('w');logs.append(f);p=subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT,start_new_session=True);procs.append(p)
def service(kind,typ,request):
 p=subprocess.run(['gz','service','-s','/world/clearing_fixture/'+kind,'--reqtype',typ,'--reptype','gz.msgs.Boolean','--timeout','4000','--req',request],capture_output=True,text=True,timeout=6)
 assert p.returncode==0 and 'data: true' in p.stdout,p.stdout+p.stderr
sdf=(Path(__file__).parent/'fixtures/clearing_lidar.sdf').read_text().replace('<pose>0 0 .5 0 0 0</pose>','<pose>.3 0 .5 0 0 0</pose>');(out/'world.sdf').write_text(sdf)
# Keep a real visible box as a control. Test box occupies the lidar's upward rays.
for name,x,y,height in [('removed_box',1.5,0.,.65),('retained_box',0.,1.5,.65)]:
 (out/(name+'.sdf')).write_text(f'<sdf version="1.8"><model name="{name}"><static>true</static><pose>{x} {y} {height/2+.005} 0 0 0</pose><link name="l"><collision name="c"><geometry><box><size>.4 .4 {height}</size></box></geometry></collision><visual name="v"><geometry><box><size>.4 .4 {height}</size></box></geometry></visual></link></model></sdf>')
configs={}
for name,filename in [('controller','controller_mppi.yaml'),('planner','planner_navfn.yaml')]:
 cfg=yaml.safe_load((root/'src/lite3_navigation/config'/filename).read_text());key='local_costmap'if name=='controller'else'global_costmap';cm=cfg[key][key]['ros__parameters'];cm.update(plugins=['static_layer','voxel_layer','inflation_layer'],update_frequency=10.,publish_frequency=10.);cm['voxel_layer']['publish_voxel_map']=False
 # This fixture tests sensor layers, not the motion controller.
 if name=='controller':cfg['controller_server']['ros__parameters']['FollowPath']['plugin']='nav2_regulated_pure_pursuit_controller::RegulatedPurePursuitController'
 (out/(name+'.yaml')).write_text(yaml.safe_dump(cfg))
rclpy.init();n=rclpy.create_node('clearing_scene_fixture');latest={};b=StaticTransformBroadcaster(n)
for parent,child,x,z in [('map','odom',0.,0.),('odom','base_footprint',0.,0.),('odom','TORSO',0.,.35),('TORSO','lidar_link',.3,.15)]:
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
maps=['/global_costmap/costmap','/local_costmap/costmap'];checks=[];result={'passed':False,'out':str(out),'robot_started':False,'rl_started':False}
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
 # Put an opaque object in front before removing the old box. The old
 # obstacle must stay remembered while the lidar cannot observe its location.
 blocker=out/'occluder.sdf'
 blocker.write_text('<sdf version="1.8"><model name="occluder"><static>true</static><pose>.8 0 .505 0 0 0</pose><link name="l"><visual name="v"><geometry><box><size>.2 .8 1</size></box></geometry></visual><collision name="c"><geometry><box><size>.2 .8 1</size></box></geometry></collision></link></model></sdf>')
 service('create','gz.msgs.EntityFactory','sdf_filename: "'+str(blocker)+'"');spin(2)
 service('remove','gz.msgs.Entity','name: "removed_box", type: MODEL');spin(2)
 assert all(region(k,1.5,0.)==100 for k in maps),'occluded old obstacle was incorrectly cleared'
 checks.append('occluded former box is not blindly cleared')
 service('remove','gz.msgs.Entity','name: "occluder", type: MODEL');start=time.monotonic()
 try:wait(lambda:all(region(k,1.5,0.)<99 for k in maps),15)
 except AssertionError:
  result['after_remove']={k:region(k,1.5,0.)for k in maps};raise
 result['clear_wall_seconds']=time.monotonic()-start;checks.append('removed tall box cleared in both maps')
 assert all(region(k,0.,1.5)==100 for k in maps);checks.append('retained real box protected')
 assert all(region(k,-1.525,-1.525)==100 for k in maps);checks.append('static map obstacle protected')
 service('create','gz.msgs.EntityFactory','sdf_filename: "'+str(out/'removed_box.sdf')+'"')
 wait(lambda:all(region(k,1.5,0.)==100 for k in maps));spin(1)
 service('set_pose','gz.msgs.Pose','name: "removed_box", position: {x: 1.5, y: -0.8, z: .33}, orientation: {w: 1}')
 wait(lambda:all(region(k,1.5,0.)<99 and region(k,1.5,-.8)==100 for k in maps),15)
 checks.append('moving box clears old footprint and marks new footprint')
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
