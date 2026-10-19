#!/usr/bin/env python3
"""Domain215: real mission node, mocked Nav2 preemption/TF/services; no robot/UDP."""
import os,time,json,math,copy,threading,signal,subprocess,tempfile
from pathlib import Path
import rclpy
from rclpy.action import ActionClient
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from std_srvs.srv import SetBool,Trigger
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Path as RosPath
from nav2_msgs.action import ComputePathToPose,FollowPath
from lite3_interfaces.action import NavigateTask
from ament_index_python.packages import get_package_prefix
from check_mission_manager import NavMocks,get,until

class RefreshMocks(NavMocks):
    def __init__(self):
        super().__init__();self.case_plans=0;self.active_follow=None
    def plan(self,handle):
        cfg=copy.copy(self.cfg)
        with self.lock:self.metrics['plans']+=1;self.case_plans+=1;number=self.case_plans
        start=time.monotonic();delay=cfg.get('probe_delay',.04) if number>1 else .04
        while time.monotonic()-start<delay:
            if handle.is_cancel_requested:
                with self.lock:self.metrics['plan_canceled']+=1
                handle.canceled();return ComputePathToPose.Result()
            time.sleep(.01)
        result=ComputePathToPose.Result()
        if number>1 and cfg.get('probe_error'):
            result.error_code=208;handle.abort();return result
        with self.lock:x,y,_=self.pose
        gx=handle.request.goal.pose.position.x;gy=handle.request.goal.pose.position.y
        points=[(x,y),(gx,gy)]
        if number==1 and cfg.get('detour',True):points=[(x,y),(x,cfg.get('detour_height',2.)),(gx,cfg.get('detour_height',2.)),(gx,gy)]
        if number>1 and cfg.get('bad_goal'):points[-1]=(gx+2.,gy)
        result.path=RosPath();result.path.header.frame_id='map'
        for x,y in points:
            p=PoseStamped();p.header.frame_id='map';p.pose.position.x=x;p.pose.position.y=y;p.pose.orientation=handle.request.goal.pose.orientation;result.path.poses.append(p)
        handle.succeed();return result
    def follow(self,handle):
        cfg=copy.copy(self.cfg)
        with self.lock:
            self.active_follow=handle;self.metrics['follows']+=1;number=self.metrics['follows'];self.metrics['paths'].append(copy.deepcopy(handle.request.path))
        start=time.monotonic();duration=cfg.get('duration',20.)
        while time.monotonic()-start<duration:
            if handle.is_cancel_requested:
                with self.lock:self.metrics['follow_canceled']+=1
                handle.canceled();return FollowPath.Result()
            if self.active_follow!=handle:
                handle.abort();return FollowPath.Result()  # Native action preemption retires the old handle.
            feedback=FollowPath.Feedback();feedback.distance_to_goal=6.;feedback.speed=.32;handle.publish_feedback(feedback);time.sleep(.02)
        p=handle.request.path.poses[-1].pose
        with self.lock:self.pose=(p.position.x,p.position.y,0.)
        time.sleep(.12);handle.succeed();return FollowPath.Result()


def main():
    assert os.environ.get('ROS_DOMAIN_ID')=='215'
    rclpy.init();node=Node('route_refresh_client');m=RefreshMocks();executor=MultiThreadedExecutor(num_threads=8);executor.add_node(node);executor.add_node(m);thread=threading.Thread(target=executor.spin,daemon=True);thread.start()
    out=Path(tempfile.mkdtemp(prefix='lite3-route-refresh-'));log=(out/'mission.log').open('w')
    exe=Path(get_package_prefix('lite3_navigation'))/'lib/lite3_navigation/mission_manager'
    process=subprocess.Popen([str(exe),'--ros-args','-p','use_sim_time:=false','-p','route_refresh_period:=0.3','-p','route_refresh_timeout:=0.35','-p','stuck_timeout:=4.0','-p','planning_timeout:=1.0','-p','server_timeout:=1.0','-p','cleanup_timeout:=1.5'],stdout=log,stderr=subprocess.STDOUT)
    client=ActionClient(node,NavigateTask,'/navigate_task');gate=node.create_client(SetBool,'/lite3/set_navigation_enabled');state=node.create_client(Trigger,'/lite3/get_navigation_state');checks=[]
    def prepare(cfg):
        m.cfg={};m.pose=(0.,0.,0.);m.case_plans=0;time.sleep(.15);assert get(gate.call_async(SetBool.Request(data=True))).success;m.cfg=cfg
        return {k:len(v)if isinstance(v,list)else v for k,v in m.metrics.items()}
    def start(goal_x=6.):
        h=get(client.send_goal_async(NavigateTask.Goal(goal_x=goal_x,goal_y=0.,goal_yaw=0.)));assert h.accepted;return h
    def cancel(h):
        get(h.cancel_goal_async());r=get(h.get_result_async()).result;assert r.result_code==NavigateTask.Result.CANCELED,r
        until(lambda:not json.loads(get(state.call_async(Trigger.Request())).message)['busy']);return r
    try:
        assert client.wait_for_server(timeout_sec=8) and gate.wait_for_service(timeout_sec=8)
        before=prepare({});h=start();until(lambda:m.metrics['follows']>=before['follows']+2)
        time.sleep(.5);assert m.metrics['follows']==before['follows']+2
        assert m.metrics['pauses'][before['pauses']:]==[] and True not in m.metrics['stops'][before['stops']:]
        r=cancel(h);assert r.retry_count==0;checks.append('shorter path preempts once without pause/stop/recovery budget; retired result ignored')
        before=prepare({'detour':False});h=start();until(lambda:m.metrics['follows']>before['follows']);m.pose=(3.,0.,0.);time.sleep(1.1)
        assert m.metrics['plans']>=before['plans']+2 and m.metrics['follows']==before['follows']+1;cancel(h);checks.append('remaining suffix comparison does not mistake normal progress for improvement')
        for height,target,label in [(.2,2.,'absolute improvement threshold'),(.5,6.,'relative improvement threshold')]:
            before=prepare({'detour_height':height});h=start(target);time.sleep(.9)
            assert m.metrics['plans']>=before['plans']+2 and m.metrics['follows']==before['follows']+1;cancel(h);checks.append(label+' prevents marginal route churn')
        before=prepare({});h=start(.8);time.sleep(.9);assert m.metrics['plans']==before['plans']+1;cancel(h);checks.append('near-goal route is not replaced')
        for cfg,label in [({'probe_error':True},'optional planner failure'),({'probe_delay':1.},'timed out planner'),({'bad_goal':True},'wrong endpoint')]:
            before=prepare(cfg);h=start();time.sleep(1.2);assert m.metrics['follows']==before['follows']+1;assert not h.get_result_async().done();cancel(h);checks.append(label+' preserves current route')
        before=prepare({'probe_delay':1.});h=start();until(lambda:m.metrics['plans']>before['plans']+1);cancel(h);time.sleep(.6)
        assert m.metrics['follows']==before['follows']+1 and m.metrics['plan_canceled']>before['plan_canceled'];checks.append('cancel cleans in-flight background planner and prevents late route replacement')
        before=prepare({'accept_delay':.4});h=start();until(lambda:m.metrics['plans']>before['plans']+1);time.sleep(.05);cancel(h);checks.append('cancel while replacement acceptance is pending cleans both old and late new goals')
        before=prepare({'probe_delay':1.,'duration':.55});h=start();r=get(h.get_result_async()).result;assert r.result_code==0,r
        assert m.metrics['plan_canceled']>before['plan_canceled'];checks.append('arrival waits for background cancellation without disabling navigation')
        before=prepare({'probe_delay':1.});h=start();until(lambda:m.metrics['plans']>before['plans']+1);assert get(gate.call_async(SetBool.Request(data=False))).success
        r=get(h.get_result_async()).result;assert r.result_code==NavigateTask.Result.CANCELED,r;checks.append('navigation OFF cancels foreground and background tasks')
        (out/'result.json').write_text(json.dumps({'passed':True,'checks':checks,'robot_motion':False},indent=2));print('PASS',checks,'RESULT_FILE',out/'result.json',flush=True)
    finally:
        process.send_signal(signal.SIGINT)
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=5)
        log.close();executor.shutdown();m.destroy_node();node.destroy_node();rclpy.shutdown();thread.join(timeout=2)

if __name__=='__main__':main()
