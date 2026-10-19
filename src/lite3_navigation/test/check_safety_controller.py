#!/usr/bin/env python3
"""Domain209: real controller plugin + synthetic map/odom. No robot, Gazebo or UDP."""
import json, math, os, signal, subprocess, tempfile, time
from pathlib import Path
import rclpy, yaml
from ament_index_python.packages import get_package_share_directory
from geometry_msgs.msg import PoseStamped, TransformStamped, Twist
from lifecycle_msgs.srv import ChangeState
from nav_msgs.msg import Odometry, OccupancyGrid, Path as RosPath
from nav2_msgs.action import FollowPath
from rclpy.action import ActionClient
from rclpy.qos import QoSProfile, DurabilityPolicy
from tf2_ros import StaticTransformBroadcaster


def main():
    assert os.environ.get('ROS_DOMAIN_ID') == '209'
    out=Path(tempfile.mkdtemp(prefix='lite3-safety-controller-'))
    cfg=yaml.safe_load((Path(get_package_share_directory('lite3_navigation'))/'config/controller_mppi.yaml').read_text())
    cp=cfg['controller_server']['ros__parameters'];cp['use_sim_time']=False;cp['FollowPath']['visualize']=False
    cm=cfg['local_costmap']['local_costmap']['ros__parameters'];cm.update(use_sim_time=False,plugins=['static_layer','inflation_layer'])
    f=out/'params.yaml';f.write_text(yaml.safe_dump(cfg))
    rclpy.init();node=rclpy.create_node('safety_model_fixture');commands=[]
    assert not [n for n in node.get_node_names() if n != node.get_name()], 'Domain209 already in use'
    map_pub=node.create_publisher(OccupancyGrid,'/map',QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL))
    odom_pub=node.create_publisher(Odometry,'/odom',10)
    node.create_subscription(Twist,'/safety_test/cmd_vel',commands.append,10)
    tf=StaticTransformBroadcaster(node);t=TransformStamped();t.header.frame_id='odom';t.child_frame_id='base_footprint';t.transform.rotation.w=1.;tf.sendTransform(t)
    grid=OccupancyGrid();grid.header.frame_id='odom';grid.info.resolution=.05;grid.info.width=grid.info.height=160;grid.info.origin.position.x=grid.info.origin.position.y=-4.;grid.info.origin.orientation.w=1.;grid.data=[0]*25600
    wall_col=int((.65+4)/.05)
    for row in range(160):grid.data[row*160+wall_col]=100
    map_pub.publish(grid)
    actual=[0.]
    def publish():
        m=Odometry();m.header.stamp=node.get_clock().now().to_msg();m.header.frame_id='odom';m.child_frame_id='base_footprint';m.pose.pose.orientation.w=1.;m.twist.twist.linear.x=actual[0];odom_pub.publish(m)
    timer=node.create_timer(.02,publish);log=(out/'controller.log').open('w')
    proc=subprocess.Popen(['ros2','run','nav2_controller','controller_server','--ros-args','--params-file',str(f),'-r','cmd_vel:=/safety_test/cmd_vel'],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    def wait(pred,seconds=15):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            rclpy.spin_once(node,timeout_sec=.02)
            if pred():return
            if proc.poll()is not None:break
        raise AssertionError((out/'controller.log').read_text()[-4500:])
    def get(future,seconds=15):wait(future.done,seconds);return future.result()
    client=node.create_client(ChangeState,'/controller_server/change_state');action=ActionClient(node,FollowPath,'/follow_path')
    def submit(y, target_x=-1., angle=math.pi):
        path=RosPath();path.header.frame_id='odom'
        for x,yy,angle in [(0.,0.,0.),(target_x,y,angle)]:
            p=PoseStamped();p.header.frame_id='odom';p.pose.position.x=x;p.pose.position.y=yy;p.pose.orientation.z=math.sin(angle/2);p.pose.orientation.w=math.cos(angle/2);path.poses.append(p)
        goal=FollowPath.Goal(path=path,controller_id='FollowPath',goal_checker_id='goal_checker',progress_checker_id='progress_checker');h=get(action.send_goal_async(goal));assert h.accepted;return h
    try:
        wait(client.service_is_ready)
        for state in [1,3]:req=ChangeState.Request();req.transition.id=state;assert get(client.call_async(req)).success
        wait(action.server_is_ready);start=time.monotonic();wait(lambda:time.monotonic()-start>.5)
        h=submit(0.);wait(lambda:any(abs(c.angular.z)>.1 for c in commands));get(h.cancel_goal_async());get(h.get_result_async())
        first='stationary robot may rotate in free space; native Rotation Shim and MPPI loaded'
        actual[0]=.4;start=time.monotonic();wait(lambda:time.monotonic()-start>.6);commands.clear()
        h=submit(.05);reply=get(h.get_result_async(),8)
        assert reply.result.error_code==104,reply
        assert 'Measured stopping envelope blocked' in (out/'controller.log').read_text()
        assert not any(abs(c.linear.x)>.001 or abs(c.linear.y)>.001 or abs(c.angular.z)>.001 for c in commands),commands[-4:]
        # Change to a side wall: braking forward remains possible, but the
        # body's side clearance is below the configured 40cm slow distance.
        grid.data=[0]*25600
        wall_row=int((.45+4)/.05)
        for col in range(160):grid.data[wall_row*160+col]=100
        map_pub.publish(grid);start=time.monotonic();wait(lambda:time.monotonic()-start>1.0)
        commands.clear();h=submit(0.,target_x=2.,angle=0.)
        wait(lambda:'Safety buffer: clearance' in (out/'controller.log').read_text(),8)
        start=time.monotonic();wait(lambda:time.monotonic()-start>1.)
        get(h.cancel_goal_async());get(h.get_result_async())
        assert any(math.hypot(c.linear.x,c.linear.y)>.05 for c in commands)
        assert all(math.hypot(c.linear.x,c.linear.y)<=.32001 for c in commands)
        data={'passed':True,'checks':[first,'measured 0.4m/s momentum towards wall rejects turn/stop request; no nonzero output'],'buffer_speed_cap_verified':True,'actual_robot_motion':False,'gazebo_started':False,'domain':209,'log_dir':str(out)}
        (out/'result.json').write_text(json.dumps(data,indent=2));print(json.dumps(data),flush=True)
    finally:
        if proc.poll()is None:
            os.killpg(proc.pid,signal.SIGINT)
            try:proc.wait(timeout=8)
            except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=5)
        log.close();node.destroy_timer(timer);node.destroy_node();rclpy.shutdown()


if __name__=='__main__':main()
