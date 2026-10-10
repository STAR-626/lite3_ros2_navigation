#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""独立 ROS 域测试实际运动节点与 UDP 输出，不启动 Gazebo 或 RL。

运行前 source Jazzy 和工作空间；30011 端口必须空闲。
python3 /home/ma/lite3_ws/src/lite3_control/test/check_motion_modes.py
"""

import argparse
import json
import math
import os
from pathlib import Path
import signal
import socket
import struct
import subprocess
import tempfile
import time

import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rosgraph_msgs.msg import Clock
from std_srvs.srv import SetBool
from tf2_msgs.msg import TFMessage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--domain-id', type=int, default=179)
    args = parser.parse_args()
    if not 1 <= args.domain_id <= 232:
        parser.error('使用独立的非零 ROS_DOMAIN_ID，范围 1..232')

    workspace = Path(__file__).resolve().parents[3]
    executable = workspace / 'install/lite3_control/lib/lite3_control/lite3_motion_node'
    if not executable.is_file():
        raise RuntimeError('先构建 lite3_control：' + str(executable))

    # 不复用已占用的接收端口；不会抢占 RL 的速度接收器。
    receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiver.bind(('127.0.0.1', 30011))
    receiver.setblocking(False)
    output = Path(tempfile.mkdtemp(prefix='lite3-motion-modes-'))
    os.environ['ROS_DOMAIN_ID'] = str(args.domain_id)
    os.environ['ROS_LOG_DIR'] = str(output / 'ros_logs')
    process = None
    node = None
    checks = []
    logfile = (output / 'motion.log').open('w')
    try:
        rclpy.init(args=[])
        node = rclpy.create_node('motion_modes_check')
        manual = node.create_publisher(Twist, '/cmd_vel', 10)
        navigation = node.create_publisher(Twist, '/nav_cmd_vel', 10)
        clock = node.create_publisher(Clock, '/clock', 10)
        state = node.create_publisher(Odometry, '/lite3/ground_truth/odom', 10)
        mode = node.create_client(SetBool, '/lite3/set_navigation_mode')
        stop = node.create_client(SetBool, '/lite3/set_stop')
        odometry = []
        transforms = []
        node.create_subscription(Odometry, '/odom', odometry.append, 10)
        node.create_subscription(TFMessage, '/tf', transforms.append, 10)
        frozen_clock = Clock()
        frozen_clock.clock.sec = 10

        def launch():
            return subprocess.Popen(
                [str(executable), '--ros-args', '-p', 'use_sim_time:=true'],
                stdout=logfile, stderr=subprocess.STDOUT)

        process = launch()

        def samples(duration, publishers=()):
            end = time.monotonic() + duration
            next_publish = 0.0
            received = []
            while time.monotonic() < end:
                now = time.monotonic()
                if now >= next_publish:
                    clock.publish(frozen_clock)
                    for publisher, message in publishers:
                        publisher.publish(message)
                    next_publish = now + 0.03
                rclpy.spin_once(node, timeout_sec=0.005)
                while True:
                    try:
                        data = receiver.recv(2048)
                    except BlockingIOError:
                        break
                    assert len(data) == 12, f'UDP 长度错误：{len(data)}'
                    velocity = struct.unpack('=3f', data)
                    assert all(math.isfinite(v) for v in velocity), velocity
                    received.append(velocity)
            return received

        def assert_velocity(received, expected, label):
            assert len(received) >= 3, f'{label}: UDP 包不足 {len(received)}'
            assert all(
                all(abs(a - b) < 1e-6 for a, b in zip(v, expected))
                for v in received), f'{label}: {received[-8:]}'
            checks.append(label)
            print('PASS:', label, flush=True)

        def service(client, value):
            request = SetBool.Request()
            request.data = value
            future = client.call_async(request)
            deadline = time.monotonic() + 3.0
            during = []
            while not future.done() and time.monotonic() < deadline:
                during.extend(samples(0.015))
            assert future.done(), '服务答复超时'
            response = future.result()
            assert response is not None and response.success, str(response)
            # 排空服务完成前的 UDP 包，随后判断是否保持零速度。
            during.extend(samples(0.08))
            assert during and all(abs(v) < 1e-6 for v in during[-1]), during
            return response

        def ready():
            deadline = time.monotonic() + 6.0
            while time.monotonic() < deadline:
                samples(0.05)
                assert process.poll() is None, '运动节点意外退出'
                if (manual.get_subscription_count() == 1 and
                        navigation.get_subscription_count() == 1 and
                        state.get_subscription_count() == 1 and
                        mode.service_is_ready() and stop.service_is_ready()):
                    return
            raise AssertionError('ROS 接口发现超时或重复订阅者')

        def command(x, y=0.0, yaw=0.0):
            message = Twist()
            message.linear.x = float(x)
            message.linear.y = float(y)
            message.angular.z = float(yaw)
            return message

        zero = (0.0, 0.0, 0.0)
        manual_command = command(0.21, -0.13, 0.3)
        navigation_command = command(-0.4, 0.2, -0.2)
        both = ((manual, manual_command), (navigation, navigation_command))
        ready()
        assert_velocity(samples(0.25), zero, '启动持续零速度')

        samples(0.2, both)
        assert_velocity(samples(0.3, both), (0.21, -0.13, 0.3),
                        '默认手动模式，两来源同时发布只采用手动速度')

        service(mode, True)
        assert_velocity(samples(0.25), zero, '切到导航后清除已接受的手动速度')
        samples(0.2, both)
        assert_velocity(samples(0.3, both), (-0.4, 0.2, -0.2),
                        '导航模式，两来源同时发布只采用导航速度')

        samples(0.65, ((manual, manual_command),))
        assert_velocity(samples(0.25, ((manual, manual_command),)), zero,
                        '被拒绝的手动消息不延长导航速度超时，冻结仿真时钟仍停车')

        bad = command(float('nan'))
        samples(0.2, ((navigation, navigation_command), (manual, bad)))
        assert_velocity(samples(0.25, ((navigation, navigation_command), (manual, bad))),
                        (-0.4, 0.2, -0.2), '非当前来源的 NaN 不干扰有效导航速度')

        samples(0.1, ((navigation, bad),))
        assert_velocity(samples(0.25), zero, '当前导航来源的 NaN 立即清零')

        samples(0.2, ((navigation, command(2.0, -2.0, 3.0)),))
        assert_velocity(samples(0.25, ((navigation, command(2.0, -2.0, 3.0)),)),
                        (0.8, -0.8, 0.8), '导航速度三个分量保留限幅')

        service(stop, True)
        assert_velocity(samples(0.3, both), zero, '停止锁定持续拒绝两个来源')
        response = service(mode, False)
        assert '停止锁定仍然有效' in response.message, response.message
        assert_velocity(samples(0.3, both), zero, '切换模式不能解除停止锁定')
        samples(0.15)
        service(stop, False)
        assert_velocity(samples(0.25), zero, '显式解锁不恢复缓存速度')
        samples(0.15, ((manual, manual_command),))
        assert_velocity(samples(0.25, ((manual, manual_command),)),
                        (0.21, -0.13, 0.3), '解锁后新手动指令可以控制')

        samples(0.65, ((navigation, navigation_command),))
        assert_velocity(samples(0.25, ((navigation, navigation_command),)), zero,
                        '被拒绝的导航消息不延长手动速度超时')
        samples(0.15, ((manual, command(0.2)),))
        samples(0.1, ((manual, command(float('inf'))),))
        assert_velocity(samples(0.25), zero, '当前手动来源的 Inf 清零')

        # 检查新增速度回调没有破坏已实现的位置反馈和机身 TF。
        raw = Odometry()
        raw.header.frame_id = 'world'
        raw.child_frame_id = 'TORSO'
        raw.header.stamp.sec = 10
        raw.pose.pose.position.x = 1.2
        raw.pose.pose.position.y = -0.8
        raw.pose.pose.position.z = 0.35
        raw.pose.pose.orientation.w = 1.0
        raw.twist.twist.linear.x = 0.1
        raw.twist.twist.angular.z = 0.2
        samples(0.3, ((state, raw),))
        assert odometry and transforms, '未收到 odom/TF'
        latest = odometry[-1]
        assert latest.header.frame_id == 'odom'
        assert latest.child_frame_id == 'base_footprint'
        assert abs(latest.pose.pose.position.x - 1.2) < 1e-9
        assert abs(latest.twist.twist.angular.z - 0.2) < 1e-9
        tf = {t.child_frame_id: t for batch in transforms for t in batch.transforms}
        assert tf['base_footprint'].header.frame_id == 'odom'
        assert tf['TORSO'].header.frame_id == 'base_footprint'
        assert abs(tf['TORSO'].transform.translation.z - 0.35) < 1e-9
        checks.append('原 /odom 与机身 TF 保留')
        print('PASS:', checks[-1], flush=True)

        samples(0.15, ((manual, manual_command),))
        process.send_signal(signal.SIGINT)
        exiting = samples(0.25)
        process.wait(timeout=3)
        assert process.returncode == 0
        assert exiting and exiting[-1] == zero, exiting
        checks.append('正常退出最后发送零速度')
        print('PASS:', checks[-1], flush=True)

        process = launch()
        ready()
        assert_velocity(samples(0.25), zero, '重启不恢复旧速度')
        samples(0.2, both)
        assert_velocity(samples(0.3, both), (0.21, -0.13, 0.3),
                        '重启默认手动模式')
        report = {'status': 'PASS', 'checks': checks,
                  'ros_domain_id': args.domain_id,
                  'sim_clock_frozen_at_seconds': 10,
                  'scope': 'Real ROS topics/services and UDP; no Gazebo/RL movement.'}
        (output / 'result.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print('RESULT:', output, flush=True)
    finally:
        if process is not None and process.poll() is None:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        logfile.close()
        receiver.close()


if __name__ == '__main__':
    main()
