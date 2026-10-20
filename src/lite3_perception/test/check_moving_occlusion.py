"""Isolated Gazebo lidar + actual PosePublisher TF; no dog, RL or control UDP.
Domain217 / partition lite3_occlusion_20261020.
"""
import os,subprocess,signal,time,json,math,tempfile
from pathlib import Path
import rclpy,yaml,numpy as np
from geometry_msgs.msg import TransformStamped, PoseArray
from lifecycle_msgs.srv import ChangeState
from nav_msgs.msg import OccupancyGrid
from nav2_msgs.msg import VoxelGrid
from sensor_msgs.msg import PointCloud2
from sensor_msgs_py import point_cloud2
from std_msgs.msg import String
from rclpy.qos import qos_profile_sensor_data,QoSProfile,DurabilityPolicy
from tf2_ros import TransformBroadcaster
from rosgraph_msgs.msg import Clock
assert os.environ.get('ROS_DOMAIN_ID')=='217'
assert os.environ.get('GZ_PARTITION')=='lite3_occlusion_20261020'
out=Path(tempfile.mkdtemp(prefix='lite3-viewpoint-'));root=Path(__file__).resolve().parents[3];procs=[];logs=[]
def spawn(cmd,label):
 f=(out/(label+'.log')).open('w');logs.append(f);p=subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT,start_new_session=True);procs.append(p);return p
def stop(p):
 if p and p.poll()is None:
  os.killpg(p.pid,signal.SIGINT)
  try:p.wait(timeout=5)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGTERM);p.wait(timeout=5)
def service(kind,typ,request):
 p=subprocess.run(['gz','service','-s','/world/clearing_fixture/'+kind,'--reqtype',typ,'--reptype','gz.msgs.Boolean','--timeout','4000','--req',request],capture_output=True,text=True,timeout=6);assert p.returncode==0 and 'data: true'in p.stdout,p.stdout+p.stderr
sdf=(root/'src/lite3_perception/test/fixtures/clearing_lidar.sdf').read_text().replace('<pose>0 0 .5 0 0 0</pose>','<pose>1.8 0 .5 0 0 3.141592653589793</pose>');sdf=sdf.replace('<link name="l"><sensor', '<plugin filename="gz-sim-pose-publisher-system" name="gz::sim::systems::PosePublisher"><publish_model_pose>true</publish_model_pose><publish_link_pose>false</publish_link_pose><publish_nested_model_pose>false</publish_nested_model_pose><use_pose_vector_msg>true</use_pose_vector_msg><update_frequency>100</update_frequency></plugin><link name="l"><sensor')
(out/'world.sdf').write_text(sdf)
for name,x,y in [('box',0.,0.),('box_n',0.,1.1),('box_s',0.,-1.1)]:
 (out/(name+'.sdf')).write_text(f'<sdf version="1.8"><model name="{name}"><static>true</static><pose>{x} {y} .33 0 0 0</pose><link name="l"><collision name="c"><geometry><box><size>.6 .6 .65</size></box></geometry></collision><visual name="v"><geometry><box><size>.6 .6 .65</size></box></geometry></visual></link></model></sdf>')
for name,filename in [('controller','controller_mppi.yaml'),('planner','planner_navfn.yaml')]:
 cfg=yaml.safe_load((root/'src/lite3_navigation/config'/filename).read_text());key='local_costmap'if name=='controller'else'global_costmap';cm=cfg[key][key]['ros__parameters'];cm.update(plugins=['static_layer','voxel_layer','inflation_layer'],update_frequency=10.,publish_frequency=10.,always_send_full_costmap=True);cm['voxel_layer']['publish_voxel_map']=True
 if name=='controller':cm.update(width=8,height=8);cfg['controller_server']['ros__parameters']['FollowPath']['plugin']='nav2_regulated_pure_pursuit_controller::RegulatedPurePursuitController'
 (out/(name+'.yaml')).write_text(yaml.safe_dump(cfg))
rclpy.init();n=rclpy.create_node('viewpoint_fixture');latest={};frames=[];b=TransformBroadcaster(n); pose=[1.8,0.,math.pi]; clock_stamp=None
def transforms(x,y,yaw):
 global pose
 pose=[x,y,yaw]
 if clock_stamp is None:return
 for parent,child,xx,yy,z,a in [('map','odom',0.,0.,0.,0.),('odom','base_footprint',x-.3*math.cos(yaw),y-.3*math.sin(yaw),0.,yaw),('base_footprint','TORSO',0.,0.,.35,0.),('TORSO','lidar_link',.3,0.,.15,0.)]:
  t=TransformStamped();t.header.stamp=clock_stamp;t.header.frame_id=parent;t.child_frame_id=child;t.transform.translation.x=xx;t.transform.translation.y=yy;t.transform.translation.z=z;t.transform.rotation.z=math.sin(a/2);t.transform.rotation.w=math.cos(a/2);b.sendTransform(t)
def on_clock(msg):
 global clock_stamp
 clock_stamp=msg.clock

def on_pose(msg):
 global clock_stamp
 if not msg.poses:return
 clock_stamp=msg.header.stamp
 q=msg.poses[0].orientation; a=math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z));p=msg.poses[0].position
 transforms(p.x,p.y,a)
n.create_subscription(PoseArray,'/model/sensor/pose',on_pose,qos_profile_sensor_data)
n.create_subscription(Clock,'/clock',on_clock,qos_profile_sensor_data)
for topic,kind in [('/global_costmap/costmap',OccupancyGrid),('/local_costmap/costmap',OccupancyGrid),('/global_costmap/voxel_grid',VoxelGrid),('/lite3/lidar/points',PointCloud2),('/lite3/perception/clearing',PointCloud2),('/lite3/perception/obstacles',PointCloud2),('/lite3/perception/status',String)]:
 n.create_subscription(kind,topic,lambda m,k=topic:latest.update({k:m}),qos_profile_sensor_data)
mp=n.create_publisher(OccupancyGrid,'/map',QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL));m=OccupancyGrid();m.header.frame_id='map';m.info.resolution=.05;m.info.width=m.info.height=160;m.info.origin.position.x=m.info.origin.position.y=-4.;m.info.origin.orientation.w=1.;m.data=[0]*25600;mp.publish(m)
def spin(seconds):
 end=time.monotonic()+seconds
 while time.monotonic()<end:rclpy.spin_once(n,timeout_sec=.02)
def wait(pred,seconds=30):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  rclpy.spin_once(n,timeout_sec=.02)
  if pred():return
 raise AssertionError('timeout '+str(out))
def snap(name):
 g=latest['/global_costmap/costmap'];a=np.array(g.data).reshape(g.info.height,g.info.width);np.save(out/(name+'.npy'),a)
 v=latest.get('/global_costmap/voxel_grid')
 if v:(out/(name+'-voxels.json')).write_text(json.dumps({'data':list(v.data),'size_x':v.size_x,'size_y':v.size_y,'origin':[v.origin.x,v.origin.y,v.origin.z],'resolution':[v.resolutions.x,v.resolutions.y,v.resolutions.z]}))
 for topic in ['/lite3/lidar/points','/lite3/perception/clearing','/lite3/perception/obstacles']:
  if topic in latest:
   c=latest[topic];q=point_cloud2.read_points(c,skip_nans=False);np.save(out/(name+topic.replace('/','_')+'.npy'),q)
 return a
per=None;result={'out':str(out),'robot_started':False,'forecast_enabled':False,'samples':[]}
try:
 spawn(['gz','sim','-s','-r','--headless-rendering',str(out/'world.sdf')],'gazebo')
 spawn(['ros2','run','ros_gz_bridge','parameter_bridge','/clearing_fixture/lidar/points@sensor_msgs/msg/PointCloud2[gz.msgs.PointCloudPacked','/world/clearing_fixture/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock','/model/sensor/pose@geometry_msgs/msg/PoseArray[gz.msgs.Pose_V','--ros-args','-r','/clearing_fixture/lidar/points:=/lite3/lidar/points','-r','/world/clearing_fixture/clock:=/clock'],'bridge')
 def start_per():return spawn(['ros2','run','lite3_perception','pointcloud_obstacles','--ros-args','--params-file',str(root/'install/lite3_perception/share/lite3_perception/config/flat_ground.yaml'),'-p','forecast_enabled:=false'],'perception-'+str(len(procs)))
 per=start_per()
 for label,pkg,exe in [('controller','nav2_controller','controller_server'),('planner','nav2_planner','planner_server')]:
  spawn(['ros2','run',pkg,exe,'--ros-args','--params-file',str(out/(label+'.yaml'))],label);client=n.create_client(ChangeState,'/'+exe+'/change_state');wait(client.service_is_ready)
  for state in [1,3]:
   req=ChangeState.Request();req.transition.id=state;f=client.call_async(req);wait(f.done);assert f.result().success
 wait(lambda:'/lite3/lidar/points'in latest and '/global_costmap/costmap'in latest)
 for name in ['box','box_n','box_s']:service('create','gz.msgs.EntityFactory','sdf_filename: "'+str(out/(name+'.sdf'))+'"')
 spin(4);before=snap('east_before');g=latest['/global_costmap/costmap'];xs=g.info.origin.position.x+(np.arange(g.info.width)+.5)*g.info.resolution;ys=g.info.origin.position.y+(np.arange(g.info.height)+.5)*g.info.resolution;xx,yy=np.meshgrid(xs,ys);rear=(xx>.26)&(xx<.36)&(abs(yy)<.29)&(before==100)
 print('baseline_rear_cells',int(rear.sum()),flush=True);assert rear.sum()>4
 # Pause physical time while changing pose; TF comes from actual PosePublisher stamps.
 for k,(x,y,yaw)in enumerate([(-1.8,0.,0.),(-1.6,.6,-.35),(-1.8,0.,0.)]):
  stop(per);service('control','gz.msgs.WorldControl','pause: true');service('set_pose','gz.msgs.Pose',f'name: "sensor", position: {{x:{x}, y:{y}, z:.5}}, orientation: {{z:{math.sin(yaw/2)}, w:{math.cos(yaw/2)}}}');transforms(x,y,yaw);spin(.5);per=start_per();spin(.5);service('control','gz.msgs.WorldControl','pause: false');spin(3)
  a=snap('west_'+str(k));result['samples'].append({'pose':[x,y,yaw],'rear_original':int(rear.sum()),'rear_retained':int(((a==100)&rear).sum())});print(result['samples'][-1],flush=True)
 for k,ang in enumerate(np.linspace(math.pi,math.pi*2,25)):
  x=1.8*math.cos(ang);y=1.8*math.sin(ang);yaw=ang+math.pi
  service('set_pose','gz.msgs.Pose',f'name: "sensor", position: {{x:{x}, y:{y}, z:.5}}, orientation: {{z:{math.sin(yaw/2)}, w:{math.cos(yaw/2)}}}')
  spin(.35);a=snap('arc_'+str(k));result['samples'].append({'pose':[x,y,yaw],'rear_original':int(rear.sum()),'rear_retained':int(((a==100)&rear).sum())})
 print('arc_retained',[q['rear_retained']for q in result['samples'][3:]],flush=True)
 result['rear_retained_all']=all(s['rear_retained']==s['rear_original']for s in result['samples'])
 assert result['rear_retained_all'], 'existing surface cells flickered during viewpoint changes'
 # After observing the far face, hide it behind a nearer physical occluder.
 service('set_pose','gz.msgs.Pose','name: "sensor", position: {x:-1.8,y:0,z:.5}, orientation: {w:1}')
 spin(2)
 (out/'occluder.sdf').write_text('<sdf version="1.8"><model name="occluder"><static>true</static><pose>-.8 0 .505 0 0 0</pose><link name="l"><visual name="v"><geometry><box><size>.2 .8 1</size></box></geometry></visual><collision name="c"><geometry><box><size>.2 .8 1</size></box></geometry></collision></link></model></sdf>')
 service('create','gz.msgs.EntityFactory','sdf_filename: "'+str(out/'occluder.sdf')+'"');spin(1)
 service('remove','gz.msgs.Entity','name: "box", type: MODEL');spin(1.5)
 a=snap('hidden_removed');result['hidden_old_rear_retained']=int(((a==100)&rear).sum())
 assert result['hidden_old_rear_retained']==int(rear.sum()),'occluded old face was cleared'
 service('remove','gz.msgs.Entity','name: "occluder", type: MODEL');spin(1)
 # At 2.1m distance, the -3-degree and 0-degree scan rows straddle the
 # historical 0.4-0.5m voxel. A visible XY column is not 3D free evidence.
 # Move closer so a real downward beam crosses this remaining height slice.
 service('set_pose','gz.msgs.Pose','name: "sensor", position: {x:-1.0,y:0,z:.5}, orientation: {w:1}');start=time.monotonic()
 wait(lambda: np.all(np.array(latest['/global_costmap/costmap'].data).reshape(before.shape)[rear]<100),15)
 result['visible_remove_clear_wall_seconds']=time.monotonic()-start
 result['checks']=['25 moving viewpoints preserve existing box face','near occluder preserves removed hidden old face','removing occluder allows visible old face clearing']
 result['passed']=True
finally:
 if '/global_costmap/costmap' in latest:
  final=snap('final');result['final_old_face_costs']=final[rear].tolist() if 'rear' in globals() else []
 (out/'result.json').write_text(json.dumps(result,indent=2));print('RESULT_FILE',out/'result.json',flush=True)
 for p in reversed(procs):stop(p)
 for f in logs:f.close()
 n.destroy_node();rclpy.shutdown()
