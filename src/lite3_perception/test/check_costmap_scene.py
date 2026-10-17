#!/usr/bin/env python3
"""隔离真实仿真集成检查；会加/删测试箱子，绝不在用户默认域运行。
先在ROS域192/GZ分区lite3_3d_validation_20261014启动无GUI simulation。
"""
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import time

import numpy as np
import rclpy
from ament_index_python.packages import get_package_share_directory
from lifecycle_msgs.srv import ChangeState
from nav_msgs.msg import OccupancyGrid, Odometry
from rclpy.qos import qos_profile_sensor_data, QoSProfile, DurabilityPolicy
from rclpy.time import Time
from sensor_msgs.msg import PointCloud2, LaserScan
from sensor_msgs_py import point_cloud2
from tf2_ros import Buffer, TransformListener


def main():
    assert os.environ.get('ROS_DOMAIN_ID') in ('192', '193', '194')
    assert os.environ.get('GZ_PARTITION') == 'lite3_3d_validation_20261014'
    nav = Path(get_package_share_directory('lite3_navigation'))
    gz = Path(get_package_share_directory('lite3_gazebo'))
    processes = []
    logs = []
    names = []
    rclpy.init()
    node = rclpy.create_node('costmap_scene_probe')
    buffer = Buffer()
    listener = TransformListener(buffer, node)
    latest = {}
    for topic, kind in [('/odom', Odometry), ('/lite3/lidar/points', PointCloud2),
                        ('/lite3/perception/obstacles', PointCloud2),
                        ('/lite3/perception/ground', PointCloud2), ('/scan', LaserScan),
                        ('/global_costmap/costmap', OccupancyGrid),
                        ('/local_costmap/costmap', OccupancyGrid)]:
        qos = qos_profile_sensor_data if kind in (PointCloud2, LaserScan) else 1
        node.create_subscription(kind, topic, lambda msg, key=topic: latest.__setitem__(key, msg), qos)

    def wait(condition, timeout=25):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            rclpy.spin_once(node, timeout_sec=0.05)
            if condition():
                return
        raise AssertionError('等待真实仿真条件超时')

    def spawn(command, label):
        log = open('/tmp/lite3-3d-' + label + '.log', 'w')
        logs.append(log)
        processes.append(subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                          start_new_session=True))

    def transition(name, number):
        client = node.create_client(ChangeState, '/' + name + '/change_state')
        assert client.wait_for_service(timeout_sec=10), name
        request = ChangeState.Request()
        request.transition.id = number
        future = client.call_async(request)
        wait(future.done, 30)
        assert future.result().success, name
        node.destroy_client(client)

    def service(path, request_type, request):
        result = subprocess.run(['gz', 'service', '-s', '/world/large_warehouse/' + path,
            '--reqtype', request_type, '--reptype', 'gz.msgs.Boolean', '--timeout', '4000',
            '--req', request], capture_output=True, text=True, timeout=6)
        assert result.returncode == 0 and 'data: true' in result.stdout, result.stdout + result.stderr

    def box(name, x, y, z, size):
        filename = '/tmp/' + name + '.sdf'
        Path(filename).write_text(f'<sdf version="1.8"><model name="{name}"><static>true</static>'
            f'<pose>{x} {y} {z} 0 0 0</pose><link name="link">'
            f'<visual name="v"><geometry><box><size>{size}</size></box></geometry></visual>'
            f'<collision name="c"><geometry><box><size>{size}</size></box></geometry></collision>'
            '</link></model></sdf>')
        service('create', 'gz.msgs.EntityFactory', f'sdf_filename: "{filename}"')
        names.append(name)

    def remove(name):
        service('remove', 'gz.msgs.Entity', f'name: "{name}", type: MODEL')
        names.remove(name)

    def region(message, x, y, radius=.13):
        info = message.info
        values = []
        for xx in np.arange(x-radius, x+radius, info.resolution/2):
            for yy in np.arange(y-radius, y+radius, info.resolution/2):
                mx = int(math.floor((xx-info.origin.position.x)/info.resolution))
                my = int(math.floor((yy-info.origin.position.y)/info.resolution))
                if 0 <= mx < info.width and 0 <= my < info.height:
                    values.append(message.data[my*info.width+mx])
        assert values
        return max(values)

    try:
        spawn(['ros2', 'run', 'tf2_ros', 'static_transform_publisher', '--x', '0', '--y', '0',
               '--z', '0', '--roll', '0', '--pitch', '0', '--yaw', '0',
               '--frame-id', 'map', '--child-frame-id', 'odom'], 'map-tf')
        spawn(['ros2', 'run', 'nav2_map_server', 'map_server', '--ros-args',
               '-p', 'yaml_filename:=' + str(gz/'maps/large_warehouse.yaml'),
               '-p', 'use_sim_time:=true', '-p', 'bond_heartbeat_period:=0.0'], 'map')
        spawn(['ros2', 'run', 'nav2_planner', 'planner_server', '--ros-args',
               '--params-file', str(nav/'config/planner.yaml')], 'planner')
        spawn(['ros2', 'run', 'nav2_controller', 'controller_server', '--ros-args',
               '--params-file', str(nav/'config/controller.yaml'), '-r', 'cmd_vel:=/nav_cmd_vel'], 'controller')
        for name in ['map_server', 'planner_server', 'controller_server']:
            transition(name, 1)
            started = time.monotonic()
            wait(lambda: time.monotonic()-started > 3 and buffer.can_transform('map', 'base_footprint', Time()))
            transition(name, 3)
        wait(lambda: len(latest) == 7)
        raw = latest['/lite3/lidar/points']
        assert raw.width * raw.height == 720*31
        assert raw.header.frame_id == 'lidar_link'
        wait(lambda: buffer.can_transform('odom', 'lidar_link', Time()))
        # 使用稍早帧验证扫描时刻的TF，检查障碍高度和地面分类。
        obstacle = latest['/lite3/perception/obstacles']
        ground = latest['/lite3/perception/ground']
        wait(lambda: buffer.can_transform('odom', 'lidar_link', Time.from_msg(ground.header.stamp)))
        def heights(cloud):
            tf = buffer.lookup_transform('odom', 'lidar_link', Time.from_msg(cloud.header.stamp)).transform
            q = tf.rotation
            row = np.array([2*(q.x*q.z-q.w*q.y), 2*(q.y*q.z+q.w*q.x),
                            1-2*(q.x*q.x+q.y*q.y)])
            data = point_cloud2.read_points(cloud, field_names=('x','y','z'))
            xyz = np.column_stack([data[k].reshape(-1) for k in ('x','y','z')])
            return xyz @ row + tf.translation.z
        gh = heights(ground); oh = heights(obstacle)
        assert len(gh) > 100 and np.max(np.abs(gh-.005)) <= .02001
        assert len(oh) and oh.min() > .02499 and oh.max() <= .65001
        scan = latest['/scan']
        assert scan.header.frame_id == 'base_footprint' and len(scan.ranges) == 720
        pose = latest['/odom'].pose.pose.position
        x, y = pose.x+.9, pose.y
        maps = ['/global_costmap/costmap', '/local_costmap/costmap']
        wait(lambda: all(region(latest[k], x, y) < 99 for k in maps))
        baseline = {k:region(latest[k], x, y) for k in maps}
        low = 'lite3_low_box_' + str(os.getpid())
        box(low, x, y, .08, '.2 .3 .15')
        print('box', x, y, 'baseline', baseline, flush=True)
        def detected():
            values = {k:region(latest[k], x, y) for k in maps}
            if all(v == 100 for v in values.values()):
                return True
            return False
        wait(detected)
        marked = {k:region(latest[k], x, y) for k in maps}
        print('marked', marked, flush=True)
        started = time.monotonic()
        wait(lambda: time.monotonic()-started > 2)
        assert all(region(latest[k], x, y) == 100 for k in maps), '仍存在的箱子不能被地面射线误清除'
        remove(low)
        wait(lambda: all(region(latest[k], x, y) < 99 for k in maps), 20)
        cleared = {k:region(latest[k], x, y) for k in maps}
        print('cleared', cleared, flush=True)
        high = 'lite3_high_box_' + str(os.getpid())
        box(high, x, y, .85, '.2 .3 .2')  # 下沿0.75 > 0.65，不能标成障碍。
        start = time.monotonic()
        wait(lambda: time.monotonic()-start > 3)
        high_values = {k:region(latest[k], x, y) for k in maps}
        assert all(v < 99 for v in high_values.values()), high_values
        remove(high)
        result = {'passed': True, 'raw_points': raw.width*raw.height,
            'ground_points': len(gh), 'ground_height_minmax': [float(gh.min()),float(gh.max())],
            'obstacle_height_minmax': [float(oh.min()),float(oh.max())],
            'projected_scan_frame': scan.header.frame_id, 'test_box_xy':[x,y],
            'costmap_before':baseline, 'low_box_marked':marked,
            'low_box_removed':cleared, 'above_band_not_marked':high_values,
            'rl_started':False, 'motion_goal_sent':False}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        Path('/tmp/lite3-3d-costmap-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    finally:
        for name in list(names):
            remove(name)
        for p in processes:
            if p.poll() is None:
                p.send_signal(signal.SIGINT)
        for p in processes:
            try:p.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGTERM)
                p.wait(timeout=5)
        for log in logs:log.close()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
