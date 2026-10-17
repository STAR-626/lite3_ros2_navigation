#!/usr/bin/env python3
# Copyright 2026 STAR-626
# SPDX-License-Identifier: BSD-3-Clause
"""Check the real picker -> Gazebo Transport -> ROS PoseStamped chain.

Run after sourcing ROS and the workspace. Uses isolated ROS/Gazebo domains,
never starts RL, and never sends a navigation goal or velocity.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time

import rclpy
from geometry_msgs.msg import PoseStamped


def main():
    workspace = Path(__file__).resolve().parents[3]
    os.environ['ROS_DOMAIN_ID'] = os.environ.get('LITE3_TEST_ROS_DOMAIN', '182')
    os.environ['GZ_PARTITION'] = 'lite3-picker-bridge-' + str(os.getpid())
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    os.environ['QT_QUICK_BACKEND'] = 'software'
    build = Path(os.environ.get('LITE3_PICKER_TEST_BUILD', str(workspace / 'build/lite3_gazebo')))
    os.environ['GZ_GUI_PLUGIN_PATH'] = str(build)
    processes = []
    messages = []
    rclpy.init()
    node = rclpy.create_node('picker_bridge_check')
    node.create_subscription(PoseStamped, '/lite3/selected_goal', messages.append, 10)
    try:
        with tempfile.TemporaryDirectory(prefix='lite3-picker-bridge-') as directory:
            with open(Path(directory) / 'bridge.log', 'w+') as bridge_log, \
                    open(Path(directory) / 'picker.log', 'w+') as picker_log:
                processes.append(subprocess.Popen([
                    'ros2', 'run', 'ros_gz_bridge', 'parameter_bridge',
                    '/lite3/selected_goal@geometry_msgs/msg/PoseStamped[gz.msgs.Pose'],
                    stdout=bridge_log, stderr=subprocess.STDOUT, start_new_session=True))
                time.sleep(1)
                picker = subprocess.Popen([
                    str(build / 'check_target_picker')],
                    stdout=picker_log, stderr=subprocess.STDOUT, start_new_session=True)
                processes.append(picker)
                end = time.monotonic() + 15
                while time.monotonic() < end:
                    rclpy.spin_once(node, timeout_sec=0.1)
                    if picker.poll() is not None:
                        break
                picker_log.seek(0)
                assert picker.poll() == 0, picker_log.read()
                assert messages, 'No actual bridged ROS PoseStamped received'
                pose = messages[-1]
                assert pose.header.frame_id == 'map', pose.header.frame_id
                assert pose.pose.position.x == -2.5 and pose.pose.position.y == 3.25
                assert pose.pose.position.z == 0.0 and pose.pose.orientation.w == 1.0
                assert pose.header.stamp.sec > 0, 'click identity must survive the bridge'
                assert all(msg.header.stamp == messages[0].header.stamp for msg in messages)
                assert not node.get_publishers_info_by_topic('/cmd_vel')
                assert not node.get_publishers_info_by_topic('/nav_cmd_vel')
                print(json.dumps({'passed': True, 'messages': len(messages),
                                  'frame': pose.header.frame_id, 'x': pose.pose.position.x,
                                  'y': pose.pose.position.y, 'z': pose.pose.position.z,
                                  'velocity_publishers': 0}, ensure_ascii=False))
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGINT)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGTERM)
                    process.wait(timeout=5)
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
