#!/usr/bin/env python3
"""Actual mission binary + mock Nav2/TF, isolated ROS domain; no robot/UDP."""
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time

from check_mission_manager import NavMocks, get, until
import rclpy
from rclpy.action import ActionClient
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from ament_index_python.packages import get_package_prefix
from geometry_msgs.msg import PoseStamped
from std_msgs.msg import String
from std_srvs.srv import SetBool, Trigger
from lite3_interfaces.action import NavigateTask


def main():
    rclpy.init()
    node = Node('navigation_gate_test')
    time.sleep(0.4)
    assert not [name for name in node.get_node_names() if name != node.get_name()]
    mocks = NavMocks()
    executor = MultiThreadedExecutor(num_threads=8)
    executor.add_node(node)
    executor.add_node(mocks)
    thread = threading.Thread(target=executor.spin, daemon=True)
    thread.start()
    client = ActionClient(node, NavigateTask, '/navigate_task')
    gate = node.create_client(SetBool, '/lite3/set_navigation_enabled')
    state = node.create_client(Trigger, '/lite3/get_navigation_state')
    publisher = node.create_publisher(PoseStamped, '/lite3/selected_goal', 10)
    statuses = []
    node.create_subscription(String, '/lite3/navigation_status', lambda msg: statuses.append(msg.data), 10)
    executable = Path(get_package_prefix('lite3_navigation')) / 'lib/lite3_navigation/mission_manager'
    directory = Path(tempfile.mkdtemp(prefix='lite3-navigation-gate-'))
    log = (directory / 'mission.log').open('w')
    process = subprocess.Popen([str(executable), '--ros-args', '-p', 'use_sim_time:=false',
                                '-p', 'server_timeout:=1.0', '-p', 'cleanup_timeout:=0.8',
                                '-p', 'enable_replanning:=false'],
                               stdout=log, stderr=subprocess.STDOUT)
    passed = []

    def mark(name):
        passed.append(name)
        print('PASS:', name, flush=True)

    def switch(enable, success=True):
        response = get(gate.call_async(SetBool.Request(data=enable)), 5)
        assert response.success == success, response.message
        return response

    def submit(x=2.0, y=1.0, yaw=0.0):
        return get(client.send_goal_async(NavigateTask.Goal(goal_x=x, goal_y=y, goal_yaw=yaw)))

    def query():
        response = get(state.call_async(Trigger.Request()), 3)
        assert response.success
        return json.loads(response.message)

    def result(handle, code):
        assert handle.accepted
        response = get(handle.get_result_async(), 5)
        assert response.result.result_code == code, response.result
        return response.result

    def click(x=2.0, y=1.0, frame='map', stamp=None):
        pose = PoseStamped()
        ns = time.time_ns() if stamp is None else stamp
        pose.header.stamp.sec = ns // 1000000000
        pose.header.stamp.nanosec = ns % 1000000000
        pose.header.frame_id = frame
        pose.pose.position.x = x
        pose.pose.position.y = y
        pose.pose.orientation.w = 1.0
        publisher.publish(pose)
        return pose

    try:
        assert client.wait_for_server(timeout_sec=5)
        assert gate.wait_for_service(timeout_sec=5)
        assert state.wait_for_service(timeout_sec=5)
        time.sleep(0.3)
        assert query() == {'navigation_enabled': False, 'busy': False,
                           'fault_latched': False, 'switch_pending': False, 'phase': 'IDLE'}
        assert mocks.metrics['stops'] == [] and mocks.metrics['modes'] == []
        r = result(submit(), 8)
        assert 'NAVIGATION_DISABLED' in r.message and mocks.metrics['plans'] == 0
        mark('默认关闭：终端目标返回明确提示且不规划')
        old = click()
        time.sleep(0.2)
        switch(True)
        assert query()['navigation_enabled'] is True and not query()['busy']
        assert mocks.metrics['modes'] == [True] and mocks.metrics['stops'] == [False]
        publisher.publish(old)
        time.sleep(0.3)
        assert mocks.metrics['plans'] == 0
        mark('开启确认导航来源/解锁，开启之前的选点不重放')
        first = click()
        until(lambda: any(msg.startswith('RESULT 0') for msg in statuses))
        for _ in range(5):
            publisher.publish(first)
            time.sleep(0.1)
        assert mocks.metrics['plans'] == 1 and mocks.metrics['follows'] == 1
        mark('Gazebo目标完整规划跟随，同一点击重复消息只执行一次')
        click()
        until(lambda: mocks.metrics['follows'] == 2)
        until(lambda: sum(msg.startswith('RESULT 0') for msg in statuses) == 2)
        mark('相同坐标再次主动点击可以发新任务')
        for x, yaw in [(float('nan'), 0.0), (2.0, 4.0)]:
            result(submit(x=x, yaw=yaw), 3)
        assert mocks.metrics['plans'] == 2
        click(frame='odom')
        until(lambda: any('INVALID_GOAL (3)' in msg for msg in statuses))
        assert mocks.metrics['plans'] == 2
        mark('非法数字/弧度/选点坐标系返回3，不交给规划器')
        command = executable.parent / 'navigate'
        terminal = subprocess.run([str(command), '3', '1', '90'], capture_output=True,
                                  text=True, timeout=8)
        assert terminal.returncode == 0, terminal.stdout + terminal.stderr
        assert 'RESULT 0' in terminal.stdout
        assert abs(mocks.pose[2] - math.pi / 2) < 1e-6
        mark('终端X/Y/朝向入口复用任务链路')
        invalid = subprocess.run([str(command), 'abc', '1', '90'], capture_output=True,
                                 text=True, timeout=5)
        assert invalid.returncode == 3 and 'INVALID_GOAL (3)' in invalid.stderr
        mark('终端非数字输入在提交前返回明确错误')
        mocks.cfg = {'follow_delay': 10.0}
        click(5.0, 1.0)
        until(lambda: mocks.metrics['follows'] == 4)
        assert query()['busy'] is True and query()['phase'] == 'FOLLOWING'
        ignored = click(6.0, 1.0)
        rejected = submit(7.0, 1.0)
        assert not rejected.accepted
        until(lambda: any('BUSY' in msg for msg in statuses))
        switch(False)
        assert not query()['navigation_enabled'] and not query()['busy']
        assert mocks.metrics['follow_canceled'] == 1 and mocks.metrics['stops'][-1] is True
        mark('忙碌不覆盖，关闭总开关取消并确认停止')
        mark('只读查询准确区分关闭/开启/行走/清理后状态，不改变开关或运动')
        mocks.cfg = {'follow_delay': 0.1}
        switch(True)
        publisher.publish(ignored)
        time.sleep(0.3)
        assert mocks.metrics['plans'] == 4
        mark('关闭/忙碌期间目标不排队，重新开启不会执行旧点')
        mocks.cfg = {'plan_error': 204}
        assert 'Nav2码 204' in result(submit(), 3).message
        assert 'NAVIGATION_DISABLED' in result(submit(), 8).message
        switch(True)
        mocks.cfg = {'plan_error': 208}
        result(submit(), 1)
        mark('地图外目标返回3，无可达路径返回1；停止后需显式重开')
        mocks.cfg = {'mode_delay': 0.4}
        modes_before = len(mocks.metrics['modes'])
        opening = gate.call_async(SetBool.Request(data=True))
        until(lambda: len(mocks.metrics['modes']) > modes_before)
        switch(False)
        assert not get(opening).success
        assert 'NAVIGATION_DISABLED' in result(submit(), 8).message
        assert mocks.metrics['stops'][-1] is True
        mark('开启尚未结束时关闭优先，禁止迟到的开启恢复导航')
        mocks.cfg = {}
        mocks.stop_ok = False
        switch(True, success=False)
        assert 'NAVIGATION_DISABLED' in result(submit(), 8).message
        mark('解锁失败不会开启总开关')
        mocks.stop_ok = True
        mocks.publish_tf = False
        time.sleep(1.1)
        switch(True, success=False)
        mark('位姿过期时总开关不能报告开启成功')
        mocks.publish_tf = True
        mocks.cfg = {'follow_delay': 0.1, 'follow_error': 104, 'follow_error_msg': ''}
        switch(True)
        failure = result(submit(), 8)
        assert 'Nav2码 104' in failure.message and '超过允许等待时间' in failure.message
        assert not query()['navigation_enabled'] and not query()['busy']
        mark('Nav2的104空错误文本有中文解释，跟随失败后查询确认为关闭')
        output = {'passed': passed, 'count': len(passed),
                  'domain': os.environ['ROS_DOMAIN_ID'], 'actual_robot_motion': False}
        (directory / 'result.json').write_text(json.dumps(output, ensure_ascii=False, indent=2))
        print(json.dumps(output, ensure_ascii=False), 'evidence:', directory, flush=True)
    finally:
        process.terminate()
        process.wait(timeout=5)
        log.close()
        executor.shutdown(timeout_sec=2)
        thread.join(timeout=2)
        mocks.destroy_node()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
