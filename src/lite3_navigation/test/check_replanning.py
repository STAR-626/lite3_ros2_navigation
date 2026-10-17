#!/usr/bin/env python3
"""隔离域200：真实任务节点，模拟Nav2/TF/暂停服务；不启动机器人或UDP。"""
import json
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
from std_srvs.srv import SetBool, Trigger
from nav_msgs.msg import Path as RosPath
from visualization_msgs.msg import Marker
from rclpy.qos import QoSProfile, DurabilityPolicy
from lite3_interfaces.action import NavigateTask


def main():
    assert os.environ.get('ROS_DOMAIN_ID') == '200'
    rclpy.init()
    node = Node('replanning_test_client')
    time.sleep(.4)
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
    directory = Path(tempfile.mkdtemp(prefix='lite3-replanning-'))
    log = (directory/'mission.log').open('w')
    executable = Path(get_package_prefix('lite3_navigation'))/'lib/lite3_navigation/mission_manager'
    process = subprocess.Popen([str(executable), '--ros-args', '-p', 'use_sim_time:=false',
        '-p', 'enable_replanning:=true', '-p', 'max_replans:=2', '-p', 'replan_wait:=0.3',
        '-p', 'replan_wait_max:=0.6',
        '-p', 'recovery_timeout:=5.0', '-p', 'stuck_timeout:=0.7',
        '-p', 'task_timeout:=8.0', '-p', 'planning_timeout:=1.5',
        '-p', 'cleanup_timeout:=0.9', '-p', 'server_timeout:=1.0'],
        stdout=log, stderr=subprocess.STDOUT)
    passed = []
    views = {'path': [], 'hints': [], 'marker': []}
    for key, topic, typ in [('path','/lite3/navigation_path',RosPath), ('hints','/lite3/avoidance/failed_route',RosPath), ('marker','/lite3/navigation_marker',Marker)]:
        node.create_subscription(typ, topic, lambda m, k=key: views[k].append(m), QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))

    def query():
        return json.loads(get(state.call_async(Trigger.Request())).message)

    def prepare(cfg):
        mocks.cfg = {}
        mocks.publish_tf = True
        mocks.pose = (0., 0., 0.)
        time.sleep(.15)
        assert get(gate.call_async(SetBool.Request(data=True))).success
        mocks.cfg = cfg
        return {key: len(mocks.metrics[key]) if isinstance(mocks.metrics[key], list)
                else mocks.metrics[key] for key in mocks.metrics}

    def submit():
        return get(client.send_goal_async(NavigateTask.Goal(goal_x=2., goal_y=1., goal_yaw=0.)))

    def outcome(handle, code, retry=None, status=6):
        response = get(handle.get_result_async(), 12)
        assert response.result.result_code == code, response.result
        assert response.status == status, response
        if retry is not None:
            assert response.result.retry_count == retry, response.result
        assert process.poll() is None
        return response.result

    def mark(name):
        passed.append(name)
        print('PASS:', name, flush=True)

    try:
        assert client.wait_for_server(timeout_sec=6)
        assert gate.wait_for_service(timeout_sec=3) and state.wait_for_service(timeout_sec=3)
        prepare({'plan_error': 208})
        outcome(submit(), 1, 0)
        mark('初始没有路线仍返回NO_PATH，不误作动态重试')

        before = prepare({'follow_errors': [104, 0], 'follow_delay': .08})
        outcome(submit(), 0, 1, 4)
        assert mocks.metrics['plans']-before['plans'] == 2
        assert mocks.metrics['follows']-before['follows'] == 2
        assert mocks.metrics['pauses'][before['pauses']:] == [True, False]
        assert False not in mocks.metrics['stops'][before['stops']:]
        mark('控制受阻后暂停/等待/重规划/恢复；从不解除用户停止锁定')

        prepare({'follow_errors': [106, 105, 0], 'follow_delay': .08})
        outcome(submit(), 0, 2, 4)
        mark('不同可恢复控制错误可以连续恢复，返回真实重规划次数')

        before = prepare({'follow_error': 104, 'follow_delay': .08})
        outcome(submit(), 2, 2)
        assert mocks.metrics['follows']-before['follows'] == 3
        assert not query()['navigation_enabled']
        mark('持续无法执行时有限次数后返回BLOCKED并关闭总开关')

        prepare({'plan_errors': [0, 208, 0], 'follow_errors': [104, 0], 'follow_delay': .08})
        outcome(submit(), 0, 2, 4)
        mark('重规划暂时无路时保持暂停等待，后续有路恢复原目标')

        before = prepare({'follow_delays': [10., .08]})
        outcome(submit(), 0, 1, 4)
        assert mocks.metrics['follow_canceled'] > before['follow_canceled']
        mark('位置无进展主动取消旧控制，确认终止后才交接新路线')

        before = prepare({'follow_error': 104, 'follow_delay': .08})
        handle = submit()
        until(lambda: query()['phase'] == 'WAITING_OBSTACLE')
        get(handle.cancel_goal_async())
        outcome(handle, 7, 0, 5)
        time.sleep(.5)
        assert mocks.metrics['plans']-before['plans'] == 1
        mark('等待障碍期间用户取消，不会自动重新启动')

        before = prepare({'follow_errors': [104, 0], 'follow_delay': .08, 'pause_delay': .6})
        handle = submit()
        until(lambda: query()['phase'] == 'RECOVERY_RESUMING')
        get(handle.cancel_goal_async())
        outcome(handle, 7, 1, 5)
        assert mocks.metrics['follows']-before['follows'] == 1
        assert mocks.metrics['stops'][-1] is True
        mark('恢复暂停服务响应晚到，取消仍保持用户停止且不发送新FollowPath')

        before = prepare({'follow_errors': [104, 0], 'follow_delay': .08, 'pause_delay': .6})
        handle = submit()
        until(lambda: query()['phase'] == 'RECOVERY_RESUMING')
        assert get(gate.call_async(SetBool.Request(data=False))).success
        outcome(handle, 7, 1, 6)
        assert mocks.metrics['follows']-before['follows'] == 1
        assert mocks.metrics['stops'][-1] is True and not query()['navigation_enabled']
        mark('恢复阶段总开关关闭优先，晚到内部解除暂停不会解除用户停止')

        prepare({'plan_delay': 3.})
        outcome(submit(), 8, 0)
        mark('规划响应有独立期限，超时取消清理而非无限等待')

        before = prepare({'follow_delay': 10.})
        handle = submit()
        until(lambda: query()['phase'] == 'FOLLOWING')
        for step in range(1, 16):
            mocks.pose = (0., 0., .3*step)
            time.sleep(.15)
        assert mocks.metrics['plans']-before['plans'] == 1
        assert query()['phase'] == 'FOLLOWING'
        get(handle.cancel_goal_async())
        outcome(handle, 7, 0, 5)
        mark('持续原地转向及跨越正负pi仍算有效进展，不误判受阻')

        before = prepare({'plan_errors': [0, 208, 208], 'follow_error': 104, 'follow_delay': .08})
        started = time.monotonic()
        handle = submit()
        until(lambda: mocks.metrics['plans']-before['plans'] >= 2)
        first = time.monotonic()
        assert .25 <= first-started < 1.0, first-started
        until(lambda: mocks.metrics['plans']-before['plans'] >= 3)
        second = time.monotonic()
        assert .5 <= second-first < 1.2, second-first
        outcome(handle, 2, 2)
        mark('首次快速重规划，持续无路时按上限退避，仍有限次数结束')
        views['hints'].clear()
        prepare({'follow_delay': 10.})
        handle = submit()
        until(lambda: views['path'] and views['path'][-1].poses)
        assert views['path'][-1].header.frame_id == 'map'
        until(lambda: any(m.poses for m in views['hints']))
        until(lambda: views['path'] and not views['path'][-1].poses)
        outcome(handle, 2, 2)
        until(lambda: views['marker'] and 'BLOCKED' in views['marker'][-1].text)
        assert not views['path'][-1].poses and not views['hints'][-1].poses
        status = query()
        assert status['last_result_code'] == 2 and status['last_result_message']
        assert not status['navigation_enabled'] and status['phase'] == 'IDLE'
        mark('恢复清空执行路线、发布失败路段偏好；BLOCKED清空偏好并保留结果和RViz提示')

        prepare({'follow_delay': .3})
        outcome(submit(), 0, 0, 4)
        until(lambda: views['marker'] and 'ARRIVED' in views['marker'][-1].text)
        assert not views['path'][-1].poses and query()['last_result_code'] == 0
        mark('到达后清空路线并保留ARRIVED及可查询的结果')

        prepare({'plan_error': 206, 'plan_error_message': ''})
        occupied = outcome(submit(), 3, 0)
        assert '完整轮廓' in occupied.message
        prepare({'plan_error': 205})
        outcome(submit(), 2, 0)
        mark('目标完整轮廓受阻返回INVALID_GOAL，当前起点轮廓受阻返回BLOCKED')
        output = {'domain': 200, 'passed': passed, 'count': len(passed),
                  'actual_robot_motion': False, 'log_dir': str(directory)}
        (directory/'result.json').write_text(json.dumps(output, ensure_ascii=False, indent=2))
        print(json.dumps(output, ensure_ascii=False), flush=True)
    except BaseException:
        log.flush()
        print((directory/'mission.log').read_text(errors='replace')[-6500:], flush=True)
        raise
    finally:
        process.terminate()
        process.wait(timeout=5)
        log.close()
        executor.shutdown(timeout_sec=3)
        thread.join(timeout=3)
        mocks.destroy_node()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
