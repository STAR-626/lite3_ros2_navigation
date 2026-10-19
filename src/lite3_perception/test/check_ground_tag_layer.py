#!/usr/bin/env python3
"""Domain207: native voxel layer consumes semantic ground tag, no robot/UDP."""
import json,os,signal,subprocess,tempfile,time
from pathlib import Path
import rclpy,yaml
from geometry_msgs.msg import TransformStamped
from lifecycle_msgs.srv import ChangeState
from nav_msgs.msg import OccupancyGrid
from rclpy.qos import QoSProfile,DurabilityPolicy,qos_profile_sensor_data
from sensor_msgs.msg import PointField,PointCloud2
from sensor_msgs_py import point_cloud2
from std_msgs.msg import Header
from tf2_ros import StaticTransformBroadcaster


def main():
    assert os.environ.get('ROS_DOMAIN_ID')=='207'
    root=Path(__file__).resolve().parents[3];out=Path(tempfile.mkdtemp(prefix='lite3-ground-tag-'))
    cfg=yaml.safe_load((root/'src/lite3_navigation/config/controller.yaml').read_text());cfg['controller_server']['ros__parameters']['use_sim_time']=False
    local=cfg['local_costmap']['local_costmap']['ros__parameters'];local.update(use_sim_time=False,plugins=['static_layer','voxel_layer','inflation_layer'],update_frequency=10.,publish_frequency=10.)
    voxel=local['voxel_layer'];voxel['marking'].update(topic='/ground_test/mark',sensor_frame='test_lidar');voxel['clearing'].update(topic='/ground_test/clear',sensor_frame='test_lidar')
    params=out/'params.yaml';params.write_text(yaml.safe_dump(cfg));rclpy.init();node=rclpy.create_node('ground_tag_fixture');maps=[]
    node.create_subscription(OccupancyGrid,'/local_costmap/costmap',maps.append,1)
    mp=node.create_publisher(OccupancyGrid,'/map',QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL));mark=node.create_publisher(PointCloud2,'/ground_test/mark',qos_profile_sensor_data);clear=node.create_publisher(PointCloud2,'/ground_test/clear',qos_profile_sensor_data)
    tf=StaticTransformBroadcaster(node)
    for parent,child,z in [('odom','base_footprint',0.),('odom','test_lidar',.5)]:
        t=TransformStamped();t.header.frame_id=parent;t.child_frame_id=child;t.transform.translation.z=z;t.transform.rotation.w=1.;tf.sendTransform(t)
    m=OccupancyGrid();m.header.frame_id='odom';m.info.resolution=.05;m.info.width=m.info.height=120;m.info.origin.position.x=m.info.origin.position.y=-3.;m.info.origin.orientation.w=1.;m.data=[0]*14400;m.data[29*120+29]=100;mp.publish(m)
    marking=[(1.,0.,.08)];clearing=[]
    fields=[PointField(name=name,offset=4*i,datatype=PointField.FLOAT32,count=1) for i,name in enumerate(['x','y','z','ground'])]
    def publish():
        h=Header(stamp=node.get_clock().now().to_msg(),frame_id='odom');mark.publish(point_cloud2.create_cloud_xyz32(h,marking));clear.publish(point_cloud2.create_cloud(h,fields,clearing))
    timer=node.create_timer(.05,publish);log=(out/'controller.log').open('w');proc=subprocess.Popen(['ros2','run','nav2_controller','controller_server','--ros-args','--params-file',str(params)],stdout=log,stderr=subprocess.STDOUT,start_new_session=True);checks=[]
    def wait(pred,seconds=12):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            rclpy.spin_once(node,timeout_sec=.02)
            if pred():return
        raise AssertionError((out/'controller.log').read_text()[-3000:])
    def cost(x,y):
        if not maps:return -1
        g=maps[-1];i=g.info
        return max(g.data[int((y+dy-i.origin.position.y)/i.resolution)*i.width+int((x+dx-i.origin.position.x)/i.resolution)]for dx in [-.025,0,.025]for dy in[-.025,0,.025])
    try:
        client=node.create_client(ChangeState,'/controller_server/change_state');wait(client.service_is_ready)
        for state in [1,3]:
            req=ChangeState.Request();req.transition.id=state;f=client.call_async(req);wait(f.done);assert f.result().success
        wait(lambda:cost(1.,0.)==100);checks.append('low obstacle initially marked')
        marking=[];clearing=[(1.,0.,.08,0.)];started=time.monotonic();wait(lambda:time.monotonic()-started>.8);assert cost(1.,0.)==100;checks.append('non-ground low endpoint does not clear itself')
        clearing=[(1.,0.,.08,1.)];wait(lambda:cost(1.,0.)==0);checks.append('explicit ground tag survives TF/buffer and clears biased endpoint')
        marking=[(1.,0.,.40)];clearing=[];wait(lambda:cost(1.,0.)==100)
        marking=[];clearing=[(1.,0.,.005,1.)];started=time.monotonic();wait(lambda:time.monotonic()-started>.8);assert cost(1.,0.)==100;assert cost(-1.525,-1.525)==100;checks.append('floor ray preserves higher voxel and static obstacle')
        (out/'result.json').write_text(json.dumps({'passed':True,'checks':checks},indent=2));print('PASS',checks,'RESULT_FILE',out/'result.json',flush=True)
    finally:
        node.destroy_timer(timer)
        if proc.poll()is None:
            os.killpg(proc.pid,signal.SIGINT)
            try:proc.wait(timeout=8)
            except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=5)
        log.close();node.destroy_node();rclpy.shutdown()


if __name__=='__main__':main()
