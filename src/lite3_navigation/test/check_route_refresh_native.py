#!/usr/bin/env python3
"""Domain216: real mission + native Nav2 controller path preemption, fake planner/TF.
No Gazebo, RL, robot or UDP control. Synthetic odometry remains stationary.
"""
import os,time,json,math,threading,subprocess,signal,tempfile
from pathlib import Path
import rclpy,yaml
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
from rclpy.qos import QoSProfile,DurabilityPolicy
from geometry_msgs.msg import TransformStamped,PoseStamped,Twist
from nav_msgs.msg import OccupancyGrid,Odometry,Path as RosPath
from nav2_msgs.action import ComputePathToPose
from lifecycle_msgs.srv import ChangeState
from std_srvs.srv import SetBool,Trigger
from lite3_interfaces.action import NavigateTask
from tf2_ros import StaticTransformBroadcaster
from ament_index_python.packages import get_package_share_directory,get_package_prefix
from check_mission_manager import NavMocks,get,until

class PlannerMocks(NavMocks):
    def __init__(self):
        super().__init__();self.controller.destroy();self.calls=0
    def plan(self,handle):
        self.calls+=1;result=ComputePathToPose.Result();result.path=RosPath();result.path.header.frame_id='map'
        pts=[(0.,0.),(.8,1.),(2.2,1.),(3.,0.)] if self.calls==1 else [(0.,0.),(3.,0.)]
        for a,b in zip(pts[:-1],pts[1:]):
            count=max(2,math.ceil(math.hypot(b[0]-a[0],b[1]-a[1])/.05))
            for i in range(count):
                p=PoseStamped();p.header.frame_id='map';p.pose.position.x=a[0]+(b[0]-a[0])*i/count;p.pose.position.y=a[1]+(b[1]-a[1])*i/count;p.pose.orientation.w=1.;result.path.poses.append(p)
        p=PoseStamped();p.header.frame_id='map';p.pose.position.x=3.;p.pose.orientation.w=1.;result.path.poses.append(p)
        handle.succeed();return result

def main():
    assert os.environ.get('ROS_DOMAIN_ID')=='216'
    rclpy.init();n=Node('route_refresh_native_fixture');m=PlannerMocks();ex=MultiThreadedExecutor(num_threads=8);ex.add_node(n);ex.add_node(m);th=threading.Thread(target=ex.spin,daemon=True);th.start()
    out=Path(tempfile.mkdtemp(prefix='lite3-route-refresh-native-'));procs=[];logs=[];cmd=[]
    cfg=yaml.safe_load((Path(get_package_share_directory('lite3_navigation'))/'config/controller_mppi.yaml').read_text());cp=cfg['controller_server']['ros__parameters'];cp['use_sim_time']=False;cp['FollowPath']['visualize']=False;cp['progress_checker']['movement_time_allowance']=20.
    cm=cfg['local_costmap']['local_costmap']['ros__parameters'];cm.update(use_sim_time=False,plugins=['static_layer','inflation_layer']);f=out/'controller.yaml';f.write_text(yaml.safe_dump(cfg))
    tf=StaticTransformBroadcaster(n);t=TransformStamped();t.header.frame_id='map';t.child_frame_id='odom';t.transform.rotation.w=1.;tf.sendTransform(t)
    pub=n.create_publisher(OccupancyGrid,'/map',QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL));g=OccupancyGrid();g.header.frame_id='map';g.info.resolution=.05;g.info.width=g.info.height=200;g.info.origin.position.x=g.info.origin.position.y=-5.;g.info.origin.orientation.w=1.;g.data=[0]*40000;pub.publish(g)
    odom=n.create_publisher(Odometry,'/odom',10)
    def publish():
        msg=Odometry();msg.header.stamp=n.get_clock().now().to_msg();msg.header.frame_id='odom';msg.child_frame_id='base_footprint';msg.pose.pose.orientation.w=1.;odom.publish(msg)
    timer=n.create_timer(.02,publish);n.create_subscription(Twist,'/refresh_test/cmd_vel',lambda v:cmd.append((time.monotonic(),v)),10)
    def spawn(command,label):
        log=(out/(label+'.log')).open('w');logs.append(log);p=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);procs.append(p)
    try:
        spawn(['ros2','run','nav2_controller','controller_server','--ros-args','--params-file',str(f),'-r','cmd_vel:=/refresh_test/cmd_vel'],'controller')
        lc=n.create_client(ChangeState,'/controller_server/change_state');until(lc.service_is_ready)
        for state in [1,3]:req=ChangeState.Request();req.transition.id=state;assert get(lc.call_async(req)).success
        exe=Path(get_package_prefix('lite3_navigation'))/'lib/lite3_navigation/mission_manager'
        spawn([str(exe),'--ros-args','-p','use_sim_time:=false','-p','route_refresh_period:=0.8','-p','stuck_timeout:=10.0'],'mission')
        gate=n.create_client(SetBool,'/lite3/set_navigation_enabled');query=n.create_client(Trigger,'/lite3/get_navigation_state');a=ActionClient(n,NavigateTask,'/navigate_task');assert a.wait_for_server(timeout_sec=8);assert gate.wait_for_service(timeout_sec=8);assert get(gate.call_async(SetBool.Request(data=True))).success
        pauses_before=len(m.metrics['pauses']);stops_before=len(m.metrics['stops'])
        h=get(a.send_goal_async(NavigateTask.Goal(goal_x=3.,goal_y=0.,goal_yaw=0.)));assert h.accepted
        until(lambda:json.loads(get(query.call_async(Trigger.Request())).message)['route_updates']>=1,10)
        switched=time.monotonic();time.sleep(.5)
        assert not h.get_result_async().done(),'native preempted result ended parent task'
        assert m.metrics['pauses'][pauses_before:]==[] and True not in m.metrics['stops'][stops_before:]
        assert any(t>switched and math.hypot(c.linear.x,c.linear.y)+abs(c.angular.z)>.01 for t,c in cmd),'no native controller output after update'
        get(h.cancel_goal_async());reply=get(h.get_result_async()).result;assert reply.result_code==NavigateTask.Result.CANCELED,reply
        assert reply.retry_count==0
        result={'passed':True,'checks':['real Rotation Shim/MPPI controller accepts replacement FollowPath','parent task survives native old-goal preemption','native velocity output continues after replacement','no pause/stop calls for optimization; cancel remains authoritative'],'robot_motion':False,'gazebo_started':False}
        (out/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),'RESULT_FILE',out/'result.json',flush=True)
    finally:
        for p in reversed(procs):
            if p.poll()is None:
                os.killpg(p.pid,signal.SIGINT)
                try:p.wait(timeout=6)
                except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGTERM);p.wait(timeout=5)
        for log in logs:log.close()
        n.destroy_timer(timer);ex.shutdown(timeout_sec=3);m.destroy_node();n.destroy_node();rclpy.shutdown();th.join(timeout=2)

if __name__=='__main__':main()
