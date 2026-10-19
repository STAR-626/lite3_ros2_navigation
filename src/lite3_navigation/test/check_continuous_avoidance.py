#!/usr/bin/env python3
"""真实Gazebo/RL/雷达/MPPI闭环：独立197域及专用GZ分区。

会发送有限导航任务并加入测试箱子；必须先退出用户系统。箱子真值只用于验收，
不传给规划/控制器。支持moving横穿、static途中加入、clear空地基线。
"""
import argparse
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
import numpy as np
from sensor_msgs.msg import PointCloud2
from sensor_msgs_py import point_cloud2
from tf2_ros import Buffer, TransformListener
from rclpy.time import Time
from geometry_msgs.msg import PoseStamped, Twist
from nav_msgs.msg import Odometry, OccupancyGrid
from ros_gz_interfaces.msg import Contacts
from rclpy.action import ActionClient
from rclpy.qos import qos_profile_sensor_data
from std_srvs.srv import SetBool
from std_msgs.msg import String
from lite3_interfaces.action import NavigateTask


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', choices=['moving', 'static', 'clear'], default='moving')
    parser.add_argument('--turn', action='store_true', help='首个任务后追加90度方向导航')
    parser.add_argument('--user-box', action='store_true', help='复现用户1m箱子(0.6294,0.618)，仓库中途加入')
    parser.add_argument('--warehouse', action='store_true', help='使用原仓库及配套地图回归')
    parser.add_argument('--goal-x', type=float, default=-.5)
    parser.add_argument('--goal-y', type=float, default=-4.)
    parser.add_argument('--goal-yaw-deg', type=float, default=0.)
    args = parser.parse_args()
    assert os.environ.get('ROS_DOMAIN_ID') == '197'
    assert os.environ.get('GZ_PARTITION') == 'lite3_avoidance_validation_20261017'
    for port in (20001, 30010, 30011):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.bind(('127.0.0.1', port))
    root = Path(__file__).resolve().parents[3]
    directory = Path(tempfile.mkdtemp(prefix='lite3-avoidance-' + args.scenario + '-'))
    world = ET.parse(root/'src/lite3_gazebo/worlds/large_warehouse.sdf')
    w = world.getroot().find('world')
    if not args.warehouse:
        for model in list(w.findall('model')):
            if model.get('name') not in ('ground_plane', 'concrete_floor'):
                w.remove(model)
    world_path = directory/'empty.sdf'
    world.write(world_path, encoding='utf-8', xml_declaration=True)
    pgm = directory/'map.pgm'
    pgm.write_bytes(b'P5\n224 224\n255\n' + bytes([254])*(224*224))
    map_path = directory/'map.yaml'
    map_path.write_text('image: map.pgm\nmode: trinary\nresolution: 0.05\n'
                        'origin: [-5.6, -5.6, 0]\nnegate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.196\n')
    if args.warehouse:
        map_path = root/'src/lite3_gazebo/maps/large_warehouse.yaml'
    rclpy.init()
    node = rclpy.create_node('continuous_avoidance_probe')
    latest = {}
    samples = []
    audit = []
    tf_buffer = Buffer()
    tf_listener = TransformListener(tf_buffer, node)
    last_audit = 0.0
    contacts = []
    floor_contact_messages = []
    for topic, kind in [('/odom', Odometry), ('/lite3/ground_truth/odom', Odometry),
                        ('/lite3/dynamic_box/pose', PoseStamped),
                        ('/lite3/perception/obstacles', PointCloud2),
                        ('/local_costmap/costmap', OccupancyGrid), ('/global_costmap/costmap', OccupancyGrid)]:
        node.create_subscription(kind, topic, lambda m, t=topic: latest.update({t: m}), qos_profile_sensor_data)
    node.create_subscription(String, '/lite3/perception/status',
        lambda m: latest.update({'forecast_status': json.loads(m.data)}), 10)

    def contact(message):
        if message.contacts:
            floor_contact_messages.append(1)
        for item in message.contacts:
            names = (item.collision1.name, item.collision2.name)
            if any('Lite3' in name for name in names):
                contacts.append(names)
    node.create_subscription(Contacts, '/lite3/dynamic_box/contacts', contact, qos_profile_sensor_data)
    gate = node.create_client(SetBool, '/lite3/set_navigation_enabled')
    action = ActionClient(node, NavigateTask, '/navigate_task')
    logs = []
    processes = []

    def spawn(command, filename):
        log = (directory/filename).open('w')
        logs.append(log)
        p = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        processes.append(p)
        return p

    proc = spawn(['ros2', 'launch', 'lite3_navigation', 'bringup.launch.py',
        'gui:=false', 'rviz:=false', 'controller:=mppi',
        'world:=' + str(world_path), 'map_yaml:=' + str(map_path)], 'bringup.log')
    spawn(['ros2', 'run', 'ros_gz_bridge', 'parameter_bridge',
        '/lite3/dynamic_box/pose@geometry_msgs/msg/PoseStamped[gz.msgs.Pose',
        '/lite3/dynamic_box/contacts@ros_gz_interfaces/msg/Contacts[gz.msgs.Contacts',
        '--ros-args', '-r', '__node:=avoidance_test_box_bridge'], 'box-bridge.log')

    def tick():
        nonlocal last_audit
        rclpy.spin_once(node, timeout_sec=.02)
        if not args.warehouse and time.monotonic()-last_audit > .5 and '/lite3/perception/obstacles' in latest:
            # Read-only audit: empty test world has only floor, robot and box.
            # No truth coordinates are ever sent to the navigation stack.
            cloud = latest['/lite3/perception/obstacles']
            try:
                tf = tf_buffer.lookup_transform('odom', cloud.header.frame_id, Time.from_msg(cloud.header.stamp)).transform
                import sys
                sys.path.insert(0, str(root/'src/lite3_perception/scripts'))
                from pointcloud_obstacles import apply
                xyz = point_cloud2.read_points_numpy(cloud, field_names=['x','y','z'], skip_nans=True)
                world_points = apply(xyz, tf)
                distance = np.linalg.norm(xyz, axis=1)
                false = distance > .65
                if '/lite3/dynamic_box/pose' in latest:
                    bp = latest['/lite3/dynamic_box/pose'].pose.position
                    false &= ((np.abs(world_points[:,0]-bp.x) > .28) | (np.abs(world_points[:,1]-bp.y) > .28))
                audit.append({'stamp': cloud.header.stamp.sec+cloud.header.stamp.nanosec*1e-9,
                    'outside_box_count': int(false.sum()), 'outside_box_points': world_points[false][::max(1,int(false.sum())//80)].tolist()})
                last_audit = time.monotonic()
            except Exception:
                pass  # Audit cannot affect controller behaviour or readiness.
        if contacts:
            raise AssertionError('记录到机器人与箱子真实接触：' + str(contacts[:3]))
        if proc.poll() is not None:
            raise RuntimeError((directory/'bringup.log').read_text(errors='replace')[-6500:])
        if '/odom' in latest:
            p = latest['/odom'].pose.pose
            row = {'wall_time': time.monotonic(), 'x': p.position.x, 'y': p.position.y}
            q = p.orientation
            row['yaw'] = math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))
            if 'forecast_status' in latest:
                row['moving_clusters'] = latest['forecast_status'].get('moving_clusters', [])
                row['ground_plane'] = latest['forecast_status'].get('ground_plane')
            if '/lite3/dynamic_box/pose' in latest:
                b = latest['/lite3/dynamic_box/pose'].pose.position
                row['box'] = [b.x, b.y, b.z]
                if '/local_costmap/costmap' in latest:
                    grid = latest['/local_costmap/costmap']
                    vals = []
                    # A one-metre box is observed on its surface, not its hidden centre.
                    half = .5 if args.user_box else .2
                    offsets = [-half, -half+.025, 0., half-.025, half]
                    for dx in offsets:
                        for dy in offsets:
                            ix = int((b.x+dx-grid.info.origin.position.x)/grid.info.resolution)
                            iy = int((b.y+dy-grid.info.origin.position.y)/grid.info.resolution)
                            if 0 <= ix < grid.info.width and 0 <= iy < grid.info.height:
                                vals.append(int(grid.data[iy*grid.info.width+ix]))
                    if vals:
                        row['costmap_at_box'] = max(vals)
            samples.append(row)
        if '/lite3/ground_truth/odom' in latest:
            raw = latest['/lite3/ground_truth/odom'].pose.pose
            q = raw.orientation
            roll = math.atan2(2*(q.w*q.x+q.y*q.z), 1-2*(q.x*q.x+q.y*q.y))
            pitch = math.asin(max(-1., min(1., 2*(q.w*q.y-q.z*q.x))))
            if raw.position.z < .20 or abs(roll) > .65 or abs(pitch) > .65:
                raise AssertionError('机器狗姿态异常，停止验收')

    def wait(condition, timeout=100):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            tick()
            if condition():
                return
        raise AssertionError('验收等待超时：' + str(directory))

    def result(future, timeout=8):
        wait(future.done, timeout)
        return future.result()

    def gz_service(operation, kind, request):
        reply = subprocess.run(['gz', 'service', '-s', '/world/large_warehouse/' + operation,
            '--reqtype', kind, '--reptype', 'gz.msgs.Boolean', '--timeout', '4000',
            '--req', request], capture_output=True, text=True, timeout=6)
        assert reply.returncode == 0 and 'data: true' in reply.stdout, reply.stdout + reply.stderr

    def box_velocity(speed):
        subprocess.run(['gz', 'topic', '-t', '/lite3/dynamic_box/cmd_vel', '-m', 'gz.msgs.Twist',
            '-p', 'linear: {y: ' + str(speed) + '}'], check=True, timeout=5,
            stdout=subprocess.DEVNULL)

    commands = []
    node.create_subscription(Twist, '/nav_cmd_vel', lambda m: commands.append([m.linear.x,m.linear.y,m.angular.z]), 10)
    feedback = []
    output = {'scenario': args.scenario, 'warehouse': args.warehouse,
              'nav_command_fields': ['vx', 'vy', 'wz'], 'goal': [args.goal_x, args.goal_y, args.goal_yaw_deg], 'user_box': args.user_box, 'log_dir': str(directory)}
    try:
        wait(lambda: gate.service_is_ready() and action.server_is_ready() and '/odom' in latest)
        # FastDDS双向响应端点发现可能晚于service_is_ready；首个请求前等待图收敛。
        discovered = time.monotonic()
        wait(lambda: time.monotonic()-discovered > 2.0, 4)
        assert result(gate.call_async(SetBool.Request(data=True)), 15).success
        start_x = latest['/odom'].pose.pose.position.x
        goal = NavigateTask.Goal(goal_x=args.goal_x, goal_y=args.goal_y,
                                 goal_yaw=math.radians(args.goal_yaw_deg))
        handle = result(action.send_goal_async(goal,
            feedback_callback=lambda f: feedback.append({'phase': f.feedback.phase,
                'replan_count': f.feedback.replan_count})))
        assert handle.accepted
        finished = handle.get_result_async()
        spawned = False
        end = time.monotonic() + 100
        while not finished.done() and time.monotonic() < end:
            tick()
            if args.scenario != 'clear' and not spawned and latest['/odom'].pose.pose.position.x > start_x + (3.0 if args.user_box else .35):
                box_file = root/'src/lite3_gazebo/worlds/lite3_dynamic_box.sdf'
                if args.scenario == 'static':
                    box_file_copy = directory/'stationary.sdf'
                    box_file_copy.write_text(box_file.read_text().replace('-1.8 -4.6 0.205', '-1.8 -4.0 0.205'))
                    box_file = box_file_copy
                if args.user_box:
                    box_xml = ET.parse(box_file)
                    box_xml.getroot().find('model/pose').text = '0.6294 0.618 0.505 0 0 0'
                    for size in box_xml.getroot().findall('.//box/size'): size.text = '1 1 1'
                    box_file = directory/'user_box.sdf'
                    box_xml.write(box_file, encoding='utf-8', xml_declaration=True)
                gz_service('create', 'gz.msgs.EntityFactory', 'sdf_filename: "' + str(box_file) + '"')
                spawned = True
                if args.scenario == 'moving':
                    box_velocity(.18)
                print('OBSTACLE_ADDED_AFTER_MOVEMENT', args.scenario, flush=True)
            if contacts:
                raise AssertionError('记录到机器人与箱子真实接触：' + str(contacts[:3]))
        assert finished.done(), '导航任务超时'
        reply = finished.result()
        output.update({'task_status': reply.status, 'result_code': reply.result.result_code,
                       'message': reply.result.message, 'retry_count': reply.result.retry_count,
                       'robot_box_contact_count': len(contacts),
                       'contact_sensor_messages': len(floor_contact_messages), 'nav_commands': commands,
                       'feedback': feedback, 'samples': samples})
        assert reply.result.result_code == 0, reply.result
        if args.scenario != 'clear':
            assert spawned and '/lite3/dynamic_box/pose' in latest
            assert floor_contact_messages, '没有接触传感器数据，不能宣称无物理碰撞'
        if args.scenario == 'moving':
            ys = [row['box'][1] for row in samples if 'box' in row]
            assert max(ys)-min(ys) > .4, '箱子没有持续运动'
        if args.scenario != 'clear':
            assert any(row.get('costmap_at_box', 0) >= 99 for row in samples), '未记录到雷达障碍进入局部costmap'
        if args.turn:
            handle2 = result(action.send_goal_async(NavigateTask.Goal(
                goal_x=-.5, goal_y=-2., goal_yaw=math.pi/2)))
            assert handle2.accepted
            reply2 = result(handle2.get_result_async(), 90)
            output['turn_result_code'] = reply2.result.result_code
            output['turn_message'] = reply2.result.message
            assert reply2.result.result_code == 0, reply2.result
        output['robot_box_contact_count'] = len(contacts)
        output['passed'] = True
        print('PASS', args.scenario, reply.result, 'contacts', len(contacts), flush=True)
    except BaseException:
        output.update({'passed': False, 'feedback': feedback, 'samples': samples,
                       'robot_box_contacts': contacts, 'contact_sensor_messages': len(floor_contact_messages)})
        print((directory/'bringup.log').read_text(errors='replace')[-6500:], flush=True)
        raise
    finally:
        try:
            if gate.service_is_ready():
                result(gate.call_async(SetBool.Request(data=False)), 8)
        except Exception:
            pass
        from rosidl_runtime_py.convert import message_to_ordereddict
        if '/global_costmap/costmap' in latest:
            (directory/'global_costmap.json').write_text(json.dumps(message_to_ordereddict(latest['/global_costmap/costmap'])))
        (directory/'observation_audit.json').write_text(json.dumps(audit))
        (directory/'result.json').write_text(json.dumps(output, ensure_ascii=False, indent=2))
        print('RESULT_FILE', directory/'result.json', flush=True)
        for child in reversed(processes):
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGINT)
                try:
                    child.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGTERM)
                    child.wait(timeout=5)
        for log in logs:
            log.close()
        # Gazebo's wrapper can outlive ros2 launch. Reap only the process whose
        # exact temporary world path belongs to this test, never another run.
        for entry in Path('/proc').iterdir():
            if not entry.name.isdigit():
                continue
            try:
                command = (entry/'cmdline').read_bytes().replace(b'\0', b' ').split()
                if str(world_path).encode() in command and any(b'gz' in arg for arg in command):
                    os.kill(int(entry.name), signal.SIGTERM)
                    time.sleep(.5)
                    # Exact owned temporary world only; no user simulation.
                    if (entry/'cmdline').exists() and str(world_path).encode() in (entry/'cmdline').read_bytes().replace(b'\0', b' ').split():
                        os.kill(int(entry.name), signal.SIGKILL)
            except (FileNotFoundError, PermissionError, ProcessLookupError):
                pass
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
