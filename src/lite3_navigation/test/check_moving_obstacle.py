#!/usr/bin/env python3
"""Domain203/private partition: actual Gazebo box CLI start/stop/duplicate/Ctrl+C/remove.

No robot model, RL, robot UDP ports or navigation commands.
"""
import json
import os
import re
from pathlib import Path
import signal
import subprocess
import tempfile
import time

import rclpy
from geometry_msgs.msg import PoseStamped
from rclpy.qos import qos_profile_sensor_data


def main():
    assert os.environ.get('ROS_DOMAIN_ID') == '203'
    assert os.environ.get('GZ_PARTITION') == 'lite3_box_cli_validation_20261017'
    directory = Path(tempfile.mkdtemp(prefix='lite3-box-cli-'))
    world = directory/'world.sdf'
    world.write_text('''<sdf version="1.8"><world name="large_warehouse">
      <plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics"/>
      <plugin filename="gz-sim-user-commands-system" name="gz::sim::systems::UserCommands"/>
      <plugin filename="gz-sim-scene-broadcaster-system" name="gz::sim::systems::SceneBroadcaster"/>
      <model name="floor"><static>true</static><pose>0 0 -.045 0 0 0</pose><link name="floor">
      <collision name="floor"><geometry><box><size>10 10 .1</size></box></geometry></collision>
      </link></model></world></sdf>''')
    env = os.environ.copy()
    env['GZ_SIM_SYSTEM_PLUGIN_PATH'] = '/home/ma/lite3_ws/install/lite3_gazebo/lib:' + env.get('GZ_SIM_SYSTEM_PLUGIN_PATH', '')
    logs, processes, observations = [], [], []
    rclpy.init()
    node = rclpy.create_node('moving_obstacle_cli_fixture')
    node.create_subscription(PoseStamped, '/lite3/dynamic_box/pose',
        lambda m: observations.append((time.monotonic(), m.pose.position.y)), qos_profile_sensor_data)

    def spawn(command, label):
        log = (directory/(label+'.log')).open('w')
        logs.append(log)
        p = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True, env=env)
        processes.append(p)
        return p

    def wait(condition, seconds=12):
        end = time.monotonic()+seconds
        while time.monotonic() < end:
            rclpy.spin_once(node, timeout_sec=.02)
            if condition():
                return
        raise AssertionError('Box CLI timeout: '+str(directory))

    def service_remove():
        return subprocess.run(['gz', 'service', '-s', '/world/large_warehouse/remove',
            '--reqtype', 'gz.msgs.Entity', '--reptype', 'gz.msgs.Boolean', '--timeout', '3000',
            '--req', 'name: "lite3_dynamic_box", type: MODEL'], capture_output=True,
            text=True, timeout=5, env=env).stdout

    def cli(label, *extra):
        return spawn(['ros2', 'run', 'lite3_navigation', 'moving_obstacle',
            '--x', '0', '--y', '0', '--vy', '.18', *extra], label)

    def settle():
        start = time.monotonic()
        wait(lambda: time.monotonic()-start > .6)

    def exists():
        reply = subprocess.run(['gz', 'service', '-s', '/world/large_warehouse/scene/info',
            '--reqtype', 'gz.msgs.Empty', '--reptype', 'gz.msgs.Scene', '--timeout', '3000',
            '--req', ''], capture_output=True, text=True, timeout=5, env=env)
        assert reply.returncode == 0 and reply.stdout.strip()
        return bool(re.search(r'\bname:\s*"lite3_dynamic_box"', reply.stdout))

    def stopped():
        start = time.monotonic()
        wait(lambda: time.monotonic()-start > 1.)
        samples = [y for t, y in observations if t > start+.3]
        assert len(samples) >= 5 and max(samples)-min(samples) < .01, samples

    checks = []
    try:
        spawn(['gz', 'sim', '-s', '-r', str(world), '-v', '1'], 'gazebo')
        spawn(['ros2', 'run', 'ros_gz_bridge', 'parameter_bridge',
            '/lite3/dynamic_box/pose@geometry_msgs/msg/PoseStamped[gz.msgs.Pose'], 'bridge')
        started = time.monotonic()
        wait(lambda: time.monotonic()-started > 2.)
        p = cli('finite', '--seconds', '3')
        wait(lambda: p.poll() is not None)
        assert p.returncode == 0
        print('OBSERVATIONS', len(observations), observations[:2], observations[-2:], flush=True)
        assert observations and max(y for _, y in observations)-min(y for _, y in observations) > .12
        stopped()
        checks.append('finite movement stops with zero command')
        p = cli('duplicate', '--seconds', '1')
        wait(lambda: p.poll() is not None)
        assert p.returncode != 0
        stopped()
        assert 'data: true' in service_remove()
        settle()
        assert not exists()
        checks.append('existing named model refused without moving/resetting it')
        observations.clear()
        p = cli('interrupt', '--seconds', '30')
        # Remove responses are asynchronous; old DDS samples can still be queued.
        # Observe the newly created box at its reset pose before awaiting movement.
        wait(lambda: any(abs(y) < .04 for _, y in observations))
        wait(lambda: observations and observations[-1][1] > .12)
        os.killpg(p.pid, signal.SIGINT)
        wait(lambda: p.poll() is not None)
        stopped()
        assert 'data: true' in service_remove()
        settle()
        assert not exists()
        checks.append('Ctrl+C stops box')
        p = cli('remove', '--seconds', '1', '--remove')
        wait(lambda: p.poll() is not None)
        assert p.returncode == 0
        settle()
        assert not exists()
        checks.append('remove flag deletes only created box')
        (directory/'result.json').write_text(json.dumps({'passed': True, 'checks': checks}, indent=2))
        print('PASS', checks, 'RESULT_FILE', directory/'result.json', flush=True)
    finally:
        for p in reversed(processes):
            if p.poll() is None:
                os.killpg(p.pid, signal.SIGTERM)
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(p.pid, signal.SIGKILL)
                    p.wait(timeout=3)
        for entry in Path('/proc').iterdir():
            try:
                if entry.name.isdigit() and str(world).encode() in (entry/'cmdline').read_bytes().replace(b'\0', b' ').split():
                    os.kill(int(entry.name), signal.SIGKILL)
            except (FileNotFoundError, PermissionError, ProcessLookupError):
                pass
        for log in logs:
            log.close()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
