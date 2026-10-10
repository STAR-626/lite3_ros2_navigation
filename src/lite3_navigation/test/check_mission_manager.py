#!/usr/bin/env python3
"""真实任务节点 + 隔离 ROS 域中的模拟 Nav2/TF/运动服务；不发送 UDP 或真实速度。"""
import copy
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time

if not os.environ.get('ROS_DOMAIN_ID') or os.environ['ROS_DOMAIN_ID'] == '0':
    raise SystemExit('必须显式选择一个独立的非零 ROS_DOMAIN_ID，不能在实际仿真域中运行。')

import rclpy
from rclpy.action import ActionClient, ActionServer, CancelResponse, GoalResponse
from rclpy.executors import MultiThreadedExecutor
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.node import Node
from ament_index_python.packages import get_package_prefix
from geometry_msgs.msg import PoseStamped, TransformStamped
from nav2_msgs.action import ComputePathToPose, FollowPath
from nav_msgs.msg import Path as RosPath
from std_srvs.srv import SetBool
from tf2_ros import TransformBroadcaster
from lite3_interfaces.action import NavigateTask


def until(predicate, timeout=8.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError('等待条件超时')


def get(future, timeout=8.0):
    until(future.done, timeout)
    return future.result()


class NavMocks(Node):
    def __init__(self):
        super().__init__('mission_test_nav_mocks')
        self.group = ReentrantCallbackGroup()
        self.lock = threading.Lock()
        self.cfg = {}
        self.pose = (0.0, 0.0, 0.0)
        self.publish_tf = True
        self.stop_ok = True
        self.metrics = {'plans': 0, 'follows': 0, 'plan_canceled': 0,
                        'follow_canceled': 0, 'stops': [], 'modes': [], 'paths': []}
        self.tf = TransformBroadcaster(self)
        self.timer = self.create_timer(0.02, self.broadcast, callback_group=self.group)
        self.planner = ActionServer(self, ComputePathToPose, '/compute_path_to_pose',
            execute_callback=self.plan, cancel_callback=lambda _: CancelResponse.ACCEPT,
            callback_group=self.group)
        self.controller = ActionServer(self, FollowPath, '/follow_path',
            goal_callback=self.follow_accept, execute_callback=self.follow,
            cancel_callback=lambda _: CancelResponse.ACCEPT, callback_group=self.group)
        self.create_service(SetBool, '/lite3/set_stop', self.stop, callback_group=self.group)
        self.create_service(SetBool, '/lite3/set_navigation_mode', self.mode, callback_group=self.group)

    def broadcast(self):
        with self.lock:
            if not self.publish_tf:
                return
            x, y, yaw = self.pose
        t = TransformStamped()
        t.header.stamp = self.get_clock().now().to_msg()
        t.header.frame_id = 'map'
        t.child_frame_id = 'base_footprint'
        t.transform.translation.x = x
        t.transform.translation.y = y
        t.transform.rotation.z = math.sin(yaw / 2)
        t.transform.rotation.w = math.cos(yaw / 2)
        self.tf.sendTransform(t)

    def stop(self, request, response):
        with self.lock:
            self.metrics['stops'].append(request.data)
        response.success = self.stop_ok
        response.message = '模拟停止服务'
        return response

    def mode(self, request, response):
        with self.lock:
            self.metrics['modes'].append(request.data)
        response.success = True
        response.message = '模拟导航模式'
        return response

    def follow_accept(self, request):
        time.sleep(self.cfg.get('accept_delay', 0.0))
        return GoalResponse.ACCEPT

    def plan(self, handle):
        cfg = copy.copy(self.cfg)
        with self.lock:
            self.metrics['plans'] += 1
        start = time.monotonic()
        while time.monotonic() - start < cfg.get('plan_delay', 0.05):
            if handle.is_cancel_requested:
                with self.lock:
                    self.metrics['plan_canceled'] += 1
                handle.canceled()
                return ComputePathToPose.Result()
            time.sleep(0.01)
        result = ComputePathToPose.Result()
        result.error_code = cfg.get('plan_error', 0)
        if result.error_code:
            result.error_msg = '模拟规划错误'
            handle.abort()
            return result
        result.path = RosPath()
        result.path.header.frame_id = 'map'
        with self.lock:
            start_x, start_y, _ = self.pose
        for i in range(3):
            p = PoseStamped()
            p.header.frame_id = 'map'
            p.pose.position.x = start_x + (handle.request.goal.pose.position.x - start_x) * i / 2
            p.pose.position.y = start_y + (handle.request.goal.pose.position.y - start_y) * i / 2
            p.pose.orientation = handle.request.goal.pose.orientation
            result.path.poses.append(p)
        if cfg.get('empty_path'):
            result.path.poses.clear()
        handle.succeed()
        return result

    def follow(self, handle):
        cfg = copy.copy(self.cfg)
        with self.lock:
            self.metrics['follows'] += 1
            self.metrics['paths'].append(copy.deepcopy(handle.request.path))
        start = time.monotonic()
        while time.monotonic() - start < cfg.get('follow_delay', 1.2):
            if handle.is_cancel_requested and not cfg.get('ignore_cancel'):
                with self.lock:
                    self.metrics['follow_canceled'] += 1
                handle.canceled()
                return FollowPath.Result()
            feedback = FollowPath.Feedback()
            feedback.distance_to_goal = 2.0
            feedback.speed = 0.32
            handle.publish_feedback(feedback)
            time.sleep(0.03)
        result = FollowPath.Result()
        result.error_code = cfg.get('follow_error', 0)
        if result.error_code:
            result.error_msg = '模拟跟随错误'
            handle.abort()
            return result
        p = handle.request.path.poses[-1].pose
        q = p.orientation
        yaw = math.atan2(2 * (q.w*q.z + q.x*q.y), 1 - 2*(q.y*q.y + q.z*q.z))
        with self.lock:
            self.pose = (p.position.x, p.position.y, yaw)
        time.sleep(0.15)  # 让真实任务节点收到新鲜的目标 TF。
        handle.succeed()
        return result


def main():
    rclpy.init()
    client_node = Node('mission_test_client')
    time.sleep(0.4)
    existing = [n for n in client_node.get_node_names() if n != 'mission_test_client']
    if existing:
        raise RuntimeError(f'该 ROS 域已有其他节点，拒绝测试：{existing}')
    mocks = NavMocks()
    client = ActionClient(client_node, NavigateTask, '/navigate_task')
    executor = MultiThreadedExecutor(num_threads=8)
    executor.add_node(client_node)
    executor.add_node(mocks)
    spin = threading.Thread(target=executor.spin, daemon=True)
    spin.start()
    log_dir = Path(tempfile.mkdtemp(prefix='lite3-mission-action-'))
    executable = Path(get_package_prefix('lite3_navigation'))/'lib/lite3_navigation/mission_manager'
    process = None
    log_file = None
    passed = []

    def launch():
        nonlocal process, log_file
        log_file = (log_dir / f'mission-{len(passed)}.log').open('w')
        process = subprocess.Popen([str(executable), '--ros-args',
            '-p', 'use_sim_time:=false', '-p', 'task_timeout:=4.0',
            '-p', 'server_timeout:=1.0', '-p', 'cleanup_timeout:=0.8',
            '-p', 'pose_max_age:=0.5'], stdout=log_file, stderr=subprocess.STDOUT)
        assert client.wait_for_server(timeout_sec=5.0)
        time.sleep(0.35)

    def shutdown_process():
        nonlocal process
        if process is not None:
            process.terminate()
            process.wait(timeout=5)
            process = None
        if log_file:
            log_file.close()

    def submit(x=2.0, y=1.0, **fields):
        goal = NavigateTask.Goal(goal_x=x, goal_y=y, goal_yaw=0.0)
        for name, value in fields.items():
            setattr(goal, name, value)
        feedback = []
        handle = get(client.send_goal_async(goal, feedback_callback=lambda f: feedback.append(f.feedback)))
        return handle, feedback

    def result(handle, expected, status=6):
        assert handle.accepted
        response = get(handle.get_result_async(), 9.0)
        assert response.result.result_code == expected, response.result
        assert response.status == status, response
        assert process.poll() is None, '任务结束后常驻节点退出了'
        return response.result

    def mark(name):
        passed.append(name)
        print('PASS:', name, flush=True)

    try:
        launch()
        h, feedback = submit()
        time.sleep(0.25)
        rejected, _ = submit(3.0, 3.0)
        assert not rejected.accepted
        mark('忙碌时拒绝第二个目标')
        r = result(h, NavigateTask.Result.SUCCESS, 4)
        assert feedback and any(f.phase == 'FOLLOWING' for f in feedback)
        assert r.final_pose.header.frame_id == 'map' and abs(r.final_pose.pose.position.x - 2.0) < 1e-6
        assert r.retry_count == 0
        assert len(mocks.metrics['paths'][-1].poses) == 3
        assert mocks.metrics['paths'][-1].poses[-1].pose.position.x == 2.0
        mark('规划完整Path交接、反馈和真实TF最终位姿')
        mocks.cfg = {'follow_delay': 0.2}
        h, _ = submit(3.0, 1.0)
        result(h, NavigateTask.Result.SUCCESS, 4)
        mark('同一进程连续完成第二次任务')

        before = mocks.metrics['plans']
        h, _ = submit(check_start=True, start_x=99.0)
        result(h, NavigateTask.Result.START_MISMATCH)
        assert mocks.metrics['plans'] == before
        mark('可选起点不一致返回4，不请求规划')
        h, _ = submit(x=float('nan'))
        result(h, NavigateTask.Result.INVALID_GOAL)
        mark('无效目标数字返回3')

        for nav_code, expected in [(208, 1), (204, 3), (202, 8)]:
            mocks.cfg = {'plan_error': nav_code}
            h, _ = submit()
            result(h, expected)
        mark('无路/非法目标/TF错误按任务层结果分类')
        mocks.cfg = {'empty_path': True}
        h, _ = submit()
        result(h, 8)
        mark('空路线不交给控制器')
        mocks.cfg = {'follow_delay': 0.1, 'follow_error': 105}
        h, _ = submit()
        r = result(h, 8)
        assert '105' in r.message
        mark('跟随失败保留Nav2码，不误报BLOCKED或跌倒')

        mocks.cfg = {'plan_delay': 1.0}
        follows_before = mocks.metrics['follows']
        h, _ = submit()
        time.sleep(0.15)
        assert get(h.cancel_goal_async()).goals_canceling
        result(h, 7, 5)
        assert mocks.metrics['plan_canceled'] > 0 and mocks.metrics['follows'] == follows_before
        mark('规划阶段取消：锁定停止并取消规划')
        mocks.cfg = {'follow_delay': 10.0}
        before = mocks.metrics['follows']
        h, _ = submit()
        until(lambda: mocks.metrics['follows'] > before)
        get(h.cancel_goal_async())
        result(h, 7, 5)
        mark('行走阶段取消：收到下游终止后返回取消')

        mocks.cfg = {'follow_delay': 10.0, 'accept_delay': 0.45}
        h, _ = submit()
        time.sleep(0.2)
        get(h.cancel_goal_async())
        result(h, 7, 5)
        mark('控制器接受响应晚到时仍取消旧任务')
        mocks.cfg = {'follow_delay': 10.0}
        h, _ = submit()
        result(h, 6)
        mark('总时间按实际时间超时，取消控制并保持停止锁定')

        mocks.publish_tf = False
        time.sleep(0.7)
        h, _ = submit()
        result(h, 8)
        mocks.publish_tf = True
        time.sleep(0.2)
        mark('缺失/过期位姿不会启动导航')

        # 接受响应晚于清理期限：先报故障并拒绝新任务，晚到目标依然取消。
        mocks.cfg = {'follow_delay': 10.0, 'accept_delay': 1.6}
        before = mocks.metrics['follow_canceled']
        h, _ = submit()
        time.sleep(0.2)
        get(h.cancel_goal_async())
        result(h, 8, 5)
        rejected, _ = submit()
        assert not rejected.accepted
        until(lambda: mocks.metrics['follow_canceled'] > before, 4.0)
        mark('清理超时故障锁定；晚到接受响应仍取消；拒绝后续任务')
        shutdown_process()
        mocks.cfg = {'plan_error': 208}
        mocks.stop_ok = False
        launch()
        h, _ = submit()
        result(h, 8)
        rejected, _ = submit()
        assert not rejected.accepted
        mark('停止服务拒绝时不会虚假报告已安全停止')
        assert mocks.metrics['modes'] and all(mocks.metrics['modes'])
        assert mocks.metrics['stops'] and all(mocks.metrics['stops'])
        mark('任务节点只选择导航和锁定停止，从不自动解除停止')
        output = {'passed': passed, 'count': len(passed), 'domain': os.environ['ROS_DOMAIN_ID'],
                  'actual_robot_motion': False, 'log_dir': str(log_dir)}
        (log_dir/'result.json').write_text(json.dumps(output, ensure_ascii=False, indent=2))
        print(json.dumps(output, ensure_ascii=False), flush=True)
    finally:
        shutdown_process()
        executor.shutdown(timeout_sec=2)
        spin.join(timeout=2)
        mocks.destroy_node()
        client_node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
