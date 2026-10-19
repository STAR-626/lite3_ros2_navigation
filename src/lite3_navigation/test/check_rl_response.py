#!/usr/bin/env python3
"""独立197域/专用GZ分区，空地上校准真实Gazebo+RL；会执行有限速度。

必须先退出用户系统。不会连接默认ROS域，不训练或修改RL。
"""
import argparse
import importlib.util
import json
import math
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET

import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rosgraph_msgs.msg import Clock
from rclpy.qos import qos_profile_sensor_data
from std_srvs.srv import SetBool


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lateral-only',action='store_true')
    args=parser.parse_args()
    assert os.environ.get('ROS_DOMAIN_ID') == '197'
    assert os.environ.get('GZ_PARTITION') == 'lite3_avoidance_validation_20261017'
    for port in (20001, 30010, 30011):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.bind(('127.0.0.1', port))
    root = Path(__file__).resolve().parents[3]
    directory = Path(tempfile.mkdtemp(prefix='lite3-rl-response-'))
    world = ET.parse(root / 'src/lite3_gazebo/worlds/large_warehouse.sdf')
    w = world.getroot().find('world')
    for model in list(w.findall('model')):
        if model.get('name') not in ('ground_plane', 'concrete_floor'):
            w.remove(model)
    filename = directory / 'empty.sdf'
    world.write(filename, encoding='utf-8', xml_declaration=True)
    module_path = root / 'src/lite3_navigation/scripts/bringup_runtime.py'
    spec = importlib.util.spec_from_file_location('lite3_runtime', module_path)
    runtime = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runtime)
    rclpy.init()
    node = rclpy.create_node('rl_response_probe')
    latest = {}
    for topic, kind in [('/odom', Odometry), ('/clock', Clock),
                        ('/lite3/ground_truth/odom', Odometry)]:
        node.create_subscription(kind, topic, lambda m, t=topic: latest.update({t: m}),
                                 qos_profile_sensor_data)
    publisher = node.create_publisher(Twist, '/cmd_vel', 10)
    stop = node.create_client(SetBool, '/lite3/set_stop')
    rl = None
    log = (directory / 'simulation.log').open('w')
    proc = subprocess.Popen(['ros2', 'launch', 'lite3_gazebo', 'simulation.launch.py',
        'gui:=false', 'rviz:=false', 'target_picker:=false', 'paused:=false',
        'world:=' + str(filename)], stdout=log, stderr=subprocess.STDOUT,
        start_new_session=True)

    def tick():
        rclpy.spin_once(node, timeout_sec=.02)
        if rl:
            rl.pump()
        if proc.poll() is not None:
            raise RuntimeError((directory / 'simulation.log').read_text()[-3500:])

    def wait(condition, timeout=90):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            tick()
            if condition():
                return
        raise AssertionError('响应测试等待超时，日志：' + str(directory))

    def sim():
        c = latest['/clock'].clock
        return c.sec + c.nanosec / 1e9

    def pose():
        p = latest['/odom'].pose.pose
        q = p.orientation
        return (p.position.x, p.position.y,
                math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z)))

    def run(vx, wz, duration, vy=0.):
        start = sim()
        first = pose()
        positions = []
        last_send = 0.
        deadline = time.monotonic() + 40
        while sim() - start < duration:
            tick()
            if time.monotonic() - last_send > .04:
                command = Twist()
                command.linear.x = vx
                command.linear.y = vy
                command.angular.z = wz
                publisher.publish(command)
                last_send = time.monotonic()
            p = pose()
            positions.append((sim(), *p))
            raw = latest['/lite3/ground_truth/odom'].pose.pose
            q = raw.orientation
            roll = math.atan2(2*(q.w*q.x+q.y*q.z), 1-2*(q.x*q.x+q.y*q.y))
            pitch = math.asin(max(-1., min(1., 2*(q.w*q.y-q.z*q.x))))
            if raw.position.z < .20 or abs(roll) > .6 or abs(pitch) > .6:
                raise AssertionError('检测到跌倒，终止校准')
            assert time.monotonic() < deadline, '仿真时钟停滞'
        last = pose()
        distance = math.hypot(last[0]-first[0], last[1]-first[1])
        angle = math.atan2(math.sin(last[2]-first[2]), math.cos(last[2]-first[2]))
        return {'command_vx': vx, 'command_vy': vy, 'command_wz': wz, 'start_pose': first, 'sim_duration': sim()-start,
                'displacement_m': distance, 'yaw_change_rad': angle,
                'average_speed_m_s': distance/(sim()-start),
                'average_yaw_rate_rad_s': angle/(sim()-start), 'end_pose': last}

    records = []
    try:
        wait(lambda: len(latest) == 3 and stop.service_is_ready())
        future = stop.call_async(SetBool.Request(data=True))
        wait(future.done, 5)
        assert future.result().success
        rl = runtime.RLProcess('/home/ma/Lite3_rl_deploy', directory / 'rl.log')
        wait(lambda: 'Waiting for stand up' in rl.tail)
        rl.key('z')
        wait(lambda: 'standup_state' in rl.tail)
        rl.key('c')
        wait(lambda: '[ONNX ENTER]' in rl.tail)
        subprocess.run(['gz', 'topic', '-t', '/lite3/control_mode', '-m', 'gz.msgs.StringMsg',
                        '-p', 'data: "external"'], check=True, timeout=5)
        wait(lambda: '[Lite3 control] Mode: external' in
             (directory / 'simulation.log').read_text(), 10)
        future = stop.call_async(SetBool.Request(data=False))
        wait(future.done, 5)
        assert future.result().success
        run(0., 0., 1.)
        cases = [(0.,0.,2.,.30),(0.,0.,2.,-.30),(.30,0.,2.,.25)] if args.lateral_only else [(vx,wz,dur,0.) for vx,wz,dur in [(.2,0.,2.),(.32,0.,2.),(.45,0.,2.),(.6,0.,1.5),(0.,.2,2.),(0.,.4,2.),(0.,.6,2.),(.35,.4,3.)]]
        for vx, wz, duration, vy in cases:
            record = run(vx, wz, duration, vy)
            record['stop'] = run(0., 0., 1.5)
            records.append(record)
            print(json.dumps(record), flush=True)
        output = {'scope': 'Actual Gazebo+pretrained RL on empty flat ground, isolated domain197',
                  'records': records, 'log_dir': str(directory)}
        (directory / 'result.json').write_text(json.dumps(output, ensure_ascii=False, indent=2))
        print('RESULT_FILE', directory / 'result.json', flush=True)
    finally:
        zero = Twist()
        for _ in range(3):
            publisher.publish(zero)
            rclpy.spin_once(node, timeout_sec=.05)
        if rl:
            rl.close()
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGINT)
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGTERM)
                proc.wait(timeout=5)
        log.close()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
