from pathlib import Path
import os,time,json,math,tempfile
import numpy as np
import rclpy
from rclpy.qos import qos_profile_sensor_data,QoSProfile,DurabilityPolicy
from nav_msgs.msg import OccupancyGrid,Odometry,Path as RosPath
from geometry_msgs.msg import Twist
from sensor_msgs.msg import PointCloud2
from std_msgs.msg import String
from rosgraph_msgs.msg import Clock
from std_srvs.srv import Trigger
from sensor_msgs_py import point_cloud2
from rosidl_runtime_py.convert import message_to_ordereddict
from tf2_ros import Buffer,TransformListener
out=Path(tempfile.mkdtemp(prefix='lite3-stuck-readonly-20261018-'));rclpy.init();n=rclpy.create_node('lite3_readonly_diagnosis');latest={};counts={};received={}
def save(t,m):latest[t]=m;counts[t]=counts.get(t,0)+1;received[t]=time.monotonic()
for t,k in [('/global_costmap/costmap',OccupancyGrid),('/local_costmap/costmap',OccupancyGrid),('/odom',Odometry),('/lite3/ground_truth/odom',Odometry),('/lite3/perception/obstacles',PointCloud2),('/lite3/perception/forecast',PointCloud2),('/lite3/perception/status',String),('/clock',Clock),('/nav_cmd_vel',Twist),('/cmd_vel',Twist)]:n.create_subscription(k,t,lambda m,t=t:save(t,m),qos_profile_sensor_data)
for t,k in [('/map',OccupancyGrid),('/lite3/navigation_path',RosPath),('/lite3/avoidance/failed_route',RosPath),('/plan',RosPath)]:n.create_subscription(k,t,lambda m,t=t:save(t,m),QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL) if t!='/plan' else 1)
b=Buffer();tf=TransformListener(b,n);cl=n.create_client(Trigger,'/lite3/get_navigation_state');f=None;end=time.monotonic()+7
while time.monotonic()<end:
 rclpy.spin_once(n,timeout_sec=.03)
 if f is None and cl.service_is_ready():f=cl.call_async(Trigger.Request())
summary={'directory':str(out),'message_counts':counts};sim=None
if '/clock'in latest:sim=latest['/clock'].clock.sec+latest['/clock'].clock.nanosec/1e9;summary['sim_time']=sim
if f and f.done():summary['task_state']=json.loads(f.result().message)
for t,m in latest.items():
 if isinstance(m,OccupancyGrid):
  a=np.array(m.data,dtype=np.int16).reshape(m.info.height,m.info.width);np.save(out/(t.replace('/','_')+'.npy'),a);summary[t]={'info':message_to_ordereddict(m.info)}
 elif isinstance(m,PointCloud2):
  a=point_cloud2.read_points_numpy(m,field_names=['x','y','z'],skip_nans=True);np.save(out/(t.replace('/','_')+'.npy'),a);summary[t]={'frame':m.header.frame_id,'points':len(a),'stamp':message_to_ordereddict(m.header.stamp)}
  if m.header.frame_id in ('map','odom') and len(a):
   near=a[np.hypot(a[:,0]-4.,a[:,1]-3.5)<.7];summary[t]['near_goal_points']=len(near);summary[t]['near_goal_bbox']=[near.min(axis=0).tolist(),near.max(axis=0).tolist()]if len(near) else None
 elif isinstance(m,RosPath):summary[t]={'frame':m.header.frame_id,'points':len(m.poses)};(out/(t.replace('/','_')+'.json')).write_text(json.dumps(message_to_ordereddict(m)))
 elif isinstance(m,String):summary[t]=json.loads(m.data)
 elif isinstance(m,Clock):pass
 else:summary[t]=message_to_ordereddict(m)
try:summary['map_to_base']=message_to_ordereddict(b.lookup_transform('map','base_footprint',rclpy.time.Time()))
except Exception as e:summary['tf_error']=str(e)
for t in ['/global_costmap/costmap','/local_costmap/costmap','/map']:
 if t not in latest:continue
 m=latest[t];a=np.array(m.data).reshape(m.info.height,m.info.width);i=m.info;r=i.resolution;ox,oy=i.origin.position.x,i.origin.position.y
 def cost(x,y):
  ix,iy=int((x-ox)/r),int((y-oy)/r)
  return int(a[iy,ix]) if 0<=ix<i.width and 0<=iy<i.height else None
 summary[t]['goal_center_cost']=cost(4,3.5)
 hits=[]
 for dx,dy in [(dx,dy)for dx in np.arange(-.42,.421,.01)for dy in [-.2,.2]]+[(dx,dy)for dy in np.arange(-.2,.201,.01)for dx in [-.42,.42]]:
  if cost(4+dx,3.5+dy)==100:hits.append([round(4+dx,3),round(3.5+dy,3)])
 summary[t]['goal_boundary_lethal_samples']=hits
(out/'snapshot.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps(summary,ensure_ascii=False,indent=2));n.destroy_node();rclpy.shutdown()
