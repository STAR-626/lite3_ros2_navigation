import sys,time,json,math
from pathlib import Path
import numpy as np
import rclpy
from sensor_msgs.msg import PointCloud2
from sensor_msgs_py import point_cloud2
from rclpy.qos import qos_profile_sensor_data
from tf2_ros import Buffer,TransformListener
sys.path.insert(0,'/home/ma/lite3_ws/src/lite3_perception/scripts')
from pointcloud_obstacles import apply
out=Path('/tmp/lite3-stuck-readonly-20261018-d9ilw7eq');rclpy.init();n=rclpy.create_node('lite3_cloud_readonly_check');b=Buffer();l=TransformListener(b,n);pending={};records={}
for topic in ['/lite3/perception/obstacles','/lite3/perception/ground','/lite3/lidar/points']:
 n.create_subscription(PointCloud2,topic,lambda m,t=topic:pending.update({t:m}),qos_profile_sensor_data)
end=time.monotonic()+5
while time.monotonic()<end:
 rclpy.spin_once(n,timeout_sec=.02)
 for t,m in list(pending.items()):
  try:tf=b.lookup_transform('map',m.header.frame_id,rclpy.time.Time.from_msg(m.header.stamp)).transform
  except Exception:continue
  a=point_cloud2.read_points_numpy(m,field_names=['x','y','z'],skip_nans=True);a=apply(a,tf);records[t]=a
stats={}
for t,a in records.items():
 np.save(out/(t.replace('/','_')+'_world.npy'),a)
 near=a[np.hypot(a[:,0]-4,a[:,1]-3.5)<.7];floor=a[np.abs(a[:,2]-.005)<.1]
 stats[t]={'points':len(a),'near_goal_count':len(near),'near_goal_z_quantiles':np.quantile(near[:,2],[0,.25,.5,.75,1]).tolist()if len(near)else[], 'near_floor_z_quantiles':np.quantile(floor[:,2],[0,.05,.5,.95,1]).tolist()if len(floor)else[]}
 print(t,stats[t])
 if 'obstacles'in t: print('near goal sample',near[:12].tolist())
(out/'cloud_check.json').write_text(json.dumps(stats,indent=2));n.destroy_node();rclpy.shutdown()
