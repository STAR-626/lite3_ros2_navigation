#!/usr/bin/env python3
"""平地模式：真实点云过滤，保留清除射线端点，输出二维障碍投影。"""

import json
import math
import time

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from rclpy.time import Time
from sensor_msgs.msg import LaserScan, PointCloud2, PointField
from sensor_msgs_py import point_cloud2
from std_msgs.msg import Header, String
from tf2_ros import Buffer, TransformException, TransformListener
from motion_forecast import MotionForecast
from flat_ground_fit import fit_ground_plane, height_above_plane
from obstacle_evidence import ObstacleEvidence
from lidar_no_return import clearing_no_returns, rays_intersect_body


def matrix(transform):
    q = transform.rotation
    w, x, y, z = np.array([q.w, q.x, q.y, q.z], dtype=float)
    norm = math.sqrt(w*w + x*x + y*y + z*z)
    if not math.isfinite(norm) or norm < 1e-8:
        raise ValueError('无效TF四元数')
    w, x, y, z = np.array([w, x, y, z]) / norm
    rotation = np.array([
        [1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
        [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
        [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)],
    ])
    t = transform.translation
    return rotation, np.array([t.x, t.y, t.z])


def apply(points, transform):
    rotation, translation = matrix(transform)
    return points @ rotation.T + translation


def classify(points, world_points, body_points, ground, tolerance, upper,
             self_min, self_max, range_min, range_max, ground_relative_height=None, range_uncertainty=0.0):
    """返回障碍/清除/地面掩码；三个数组逐点对应，不能以雷达z直接过滤地面。"""
    finite = np.isfinite(points).all(axis=1)
    distance = np.linalg.norm(points, axis=1)
    valid = finite & (distance >= range_min) & (distance <= range_max + 1e-4)
    self_hits = ((body_points >= self_min) & (body_points <= self_max)).all(axis=1)
    valid &= ~self_hits
    height = world_points[:, 2]
    relative = height if ground_relative_height is None else ground_relative_height
    # Far floor returns carry larger projection uncertainty. Uncertain low
    # returns remain ordinary measured clearing endpoints, never tagged ground.
    obstacles = valid & (distance < range_max - 1e-3) & \
        (relative > ground + tolerance + range_uncertainty*distance) & (height <= upper)
    floor = valid & (np.abs(relative - ground) <= tolerance)
    return obstacles, valid, floor


def project(points, samples, range_min, range_max):
    """水平坐标中每个方向保留最近已观测障碍，不填补被遮挡的物体轮廓。"""
    ranges = np.full(samples, np.inf, dtype=np.float32)
    if len(points):
        distance = np.linalg.norm(points[:, :2], axis=1)
        valid = np.isfinite(distance) & (distance >= range_min) & (distance <= range_max)
        angles = np.arctan2(points[valid, 1], points[valid, 0])
        bins = np.rint((angles + math.pi) * samples / (2*math.pi)).astype(int) % samples
        np.minimum.at(ranges, bins, distance[valid])
    return ranges


class PointcloudObstacles(Node):
    def __init__(self):
        super().__init__('lite3_pointcloud_obstacles')
        defaults = {
            'ground_height': 0.005, 'ground_tolerance': 0.02,
            'max_obstacle_height': 0.65, 'min_range': 0.12, 'max_range': 12.0,
            'scan_samples': 720, 'scan_period': 0.1, 'max_cloud_age': 0.3,
            'self_min': [-0.38, -0.28, -0.50], 'self_max': [0.38, 0.28, 0.18],
            'ground_fit_enabled': True, 'ground_range_uncertainty': 0.003,
            'gazebo_no_return_clearing': True,
            'lidar_horizontal_samples': 720, 'lidar_vertical_samples': 31,
            'lidar_horizontal_min': -math.pi, 'lidar_horizontal_max': math.pi,
            'lidar_vertical_min': -math.pi/3, 'lidar_vertical_max': math.pi/6,
            'forecast_enabled': True, 'forecast_horizon': 2.5, 'forecast_padding': 0.10,
        }
        self.values = {key: self.declare_parameter(key, value).value
                       for key, value in defaults.items()}
        v = self.values
        if (not all(math.isfinite(float(v[k])) for k in defaults if k not in ('self_min', 'self_max'))
                or v['ground_tolerance'] < 0 or not 0 <= v['ground_range_uncertainty'] <= .01
                or v['max_obstacle_height'] <= v['ground_height'] + v['ground_tolerance']
                or not 0 < v['min_range'] < v['max_range']
                or v['lidar_horizontal_samples'] < 2 or v['lidar_vertical_samples'] < 2
                or v['lidar_horizontal_max'] <= v['lidar_horizontal_min']
                or v['lidar_vertical_max'] <= v['lidar_vertical_min']
                or v['scan_samples'] < 2 or v['scan_period'] <= 0 or v['max_cloud_age'] <= 0
                or not 0 < v['forecast_horizon'] <= 3 or not 0 <= v['forecast_padding'] <= .3
                or len(v['self_min']) != 3 or len(v['self_max']) != 3
                or not np.isfinite(v['self_min'] + v['self_max']).all()
                or not (np.array(v['self_min']) < np.array(v['self_max'])).all()):
            raise ValueError('无效平地感知参数')
        qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT,
                         durability=DurabilityPolicy.VOLATILE)
        self.buffer = Buffer()
        self.listener = TransformListener(self.buffer, self)
        self.pending = None
        self.last_log = 0.0
        self.obstacles = self.create_publisher(PointCloud2, '/lite3/perception/obstacles', qos)
        self.clearing = self.create_publisher(PointCloud2, '/lite3/perception/clearing', qos)
        self.ground = self.create_publisher(PointCloud2, '/lite3/perception/ground', qos)
        self.scan = self.create_publisher(LaserScan, '/scan', qos)
        self.status = self.create_publisher(String, '/lite3/perception/status', 1)
        self.obstacle_evidence = ObstacleEvidence()
        self.forecast = MotionForecast(v['forecast_horizon'], v['forecast_padding'])
        self.predicted = self.create_publisher(PointCloud2, '/lite3/perception/forecast', qos)
        self.subscription = self.create_subscription(
            PointCloud2, '/lite3/lidar/points', self.receive, qos)
        self.timer = self.create_timer(0.02, self.process)
        self.get_logger().info(
            '三维平地感知已启动：点云→地面/自身过滤→障碍与清除点云；/scan为二维障碍投影')

    def receive(self, cloud):
        self.pending = cloud  # 只处理最新帧，防止点云积压造成导航延迟。

    def notice(self, text):
        now = time.monotonic()
        if now - self.last_log > 2.0:
            self.get_logger().warn(text)
            self.last_log = now

    def process(self):
        cloud = self.pending
        if cloud is None:
            return
        stamp = Time.from_msg(cloud.header.stamp)
        age = (self.get_clock().now() - stamp).nanoseconds * 1e-9
        if age > self.values['max_cloud_age'] or age < -0.05:
            self.pending = None
            self.notice('丢弃过期/未来点云，检查仿真时钟；不重复发布旧数据')
            return
        try:
            world_tf = self.buffer.lookup_transform('odom', cloud.header.frame_id, stamp).transform
            body_tf = self.buffer.lookup_transform('TORSO', cloud.header.frame_id, stamp).transform
            flat_tf = self.buffer.lookup_transform('base_footprint', cloud.header.frame_id, stamp).transform
        except TransformException:
            # 不阻塞单线程executor；等同一帧的运动TF到达后重试。
            self.notice('等待扫描时刻TF：odom / TORSO / base_footprint')
            return
        self.pending = None
        try:
            v = self.values
            fields = point_cloud2.read_points(cloud, field_names=('x', 'y', 'z'), skip_nans=False)
            points = np.column_stack([fields[name].reshape(-1) for name in ('x', 'y', 'z')])
            # Decode organized Gazebo no-return beams before losing row/column
            # indices. These are clearing-only range limits, never obstacle hits
            # or samples for estimating the ground plane.
            no_return = clearing_no_returns(
                points, cloud.width, cloud.height,
                v['lidar_horizontal_samples'], v['lidar_vertical_samples'],
                v['lidar_horizontal_min'], v['lidar_horizontal_max'],
                v['lidar_vertical_min'], v['lidar_vertical_max'], v['max_range']
            ) if v['gazebo_no_return_clearing'] else np.empty((0, 3), np.float32)
            points = points[np.isfinite(points).all(axis=1)]
            world = apply(points, world_tf)
            body = apply(points, body_tf)
            obstacle, clear, floor = classify(
                points, world, body, v['ground_height'], v['ground_tolerance'],
                v['max_obstacle_height'], np.array(v['self_min']), np.array(v['self_max']),
                v['min_range'], v['max_range'])
            plane = None
            if v['ground_fit_enabled']:
                origin = np.array([world_tf.translation.x, world_tf.translation.y,
                                   world_tf.translation.z])
                plane = fit_ground_plane(world[clear], origin, v['ground_height'])
                if plane is None:
                    # No trustworthy floor: do not mark or clear from this scan.
                    # Existing Nav2 observation freshness stops navigation on a sustained gap.
                    self.notice('平地证据不足，暂停此帧标记/清除；不把未知地面当障碍或空闲')
                    return
                obstacle, clear, floor = classify(
                    points, world, body, v['ground_height'], v['ground_tolerance'],
                    v['max_obstacle_height'], np.array(v['self_min']), np.array(v['self_max']),
                    v['min_range'], v['max_range'],
                    height_above_plane(world, plane, v['ground_height']), v['ground_range_uncertainty'])
            raw_obstacle_count = int(obstacle.sum())
            indices = np.flatnonzero(obstacle)
            supported = self.obstacle_evidence.filter(world[obstacle], stamp.nanoseconds*1e-9)
            obstacle[indices[~supported]] = False
            # Keep measured XYZ, timestamps and true lidar origin unchanged.
            for publisher, mask in ((self.obstacles, obstacle), (self.ground, floor)):
                publisher.publish(point_cloud2.create_cloud_xyz32(
                    cloud.header, points[mask].astype(np.float32)))
            # Nav2 preserves extra PointCloud2 fields. Tag the actually classified
            # ground endpoint so the voxel layer can compensate its 2-cell retreat
            # without mistaking every low obstacle for ground.
            tagged = np.column_stack([points[clear], floor[clear].astype(np.float32),
                                      np.zeros(int(clear.sum()), np.float32)])
            if len(no_return):
                # The self AABB includes the lidar mount. Ignore only the
                # sensor's configured blind range, then reject rays intersecting
                # that AABB; never carve through the robot's hidden rear sector.
                body_end = apply(no_return, body_tf)
                _, body_origin = matrix(body_tf)
                direction = body_end-body_origin
                length = np.linalg.norm(direction, axis=1)
                blind_end = body_origin + direction * (v['min_range']/length)[:, None]
                visible = ~rays_intersect_body(
                    body_end, blind_end, np.array(v['self_min']), np.array(v['self_max']))
                no_return = no_return[visible]
                tagged = np.vstack([tagged, np.column_stack([
                    no_return, np.zeros(len(no_return)), np.ones(len(no_return))])])
            fields = [PointField(name=name, offset=4*i, datatype=PointField.FLOAT32, count=1)
                      for i, name in enumerate(('x', 'y', 'z', 'ground', 'no_return'))]
            self.clearing.publish(point_cloud2.create_cloud(
                cloud.header, fields, tagged.astype(np.float32)))
            flat = apply(points[obstacle], flat_tf)
            predicted = self.forecast.update(world[obstacle], stamp.nanoseconds*1e-9) \
                if v['forecast_enabled'] else np.empty((0, 3), np.float32)
            self.predicted.publish(point_cloud2.create_cloud_xyz32(
                Header(stamp=cloud.header.stamp, frame_id='odom'), predicted))
            scan = LaserScan()
            scan.header = Header(stamp=cloud.header.stamp, frame_id='base_footprint')
            scan.angle_min = -math.pi
            scan.angle_increment = 2*math.pi / v['scan_samples']
            scan.angle_max = scan.angle_min + (v['scan_samples']-1)*scan.angle_increment
            scan.scan_time = v['scan_period']
            scan.range_min, scan.range_max = v['min_range'], v['max_range']
            scan.ranges = project(flat, v['scan_samples'], v['min_range'], v['max_range']).tolist()
            self.scan.publish(scan)
            now = time.monotonic()
            if now - self.last_log > 2.0:
                self.status.publish(String(data=json.dumps({
                    'frame': cloud.header.frame_id, 'mode': 'flat_ground',
                    'finite_input': len(points), 'obstacles': int(obstacle.sum()), 'raw_obstacles': raw_obstacle_count,
                    'ground': int(floor.sum()), 'clearing': len(tagged),
                    'no_return_clearing': len(no_return),
                    'ground_plane': plane.tolist() if plane is not None else None,
                    'max_height_m': v['max_obstacle_height'],
                    'moving_clusters': self.forecast.moving,
                    'forecast_points': len(predicted),
                }, ensure_ascii=False)))
                self.last_log = now
        except (ValueError, AssertionError, KeyError) as error:
            self.notice(f'丢弃无效点云：{error}')


def main():
    rclpy.init()
    node = PointcloudObstacles()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
