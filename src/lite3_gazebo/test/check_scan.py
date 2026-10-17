#!/usr/bin/env python3
"""只读检查真实三维点云、/scan障碍投影和扫描时刻 TF；需先启动项目，不发送运动指令。"""

import json
import math
import time

import rclpy
from rclpy.qos import qos_profile_sensor_data
from rclpy.time import Time
from sensor_msgs.msg import LaserScan, PointCloud2
from tf2_ros import Buffer, TransformListener


def main():
    rclpy.init()
    node = rclpy.create_node('lite3_scan_check')
    buffer = Buffer()
    listener = TransformListener(buffer, node)
    scans = []
    clouds = []
    subscription = node.create_subscription(
        LaserScan, '/scan', scans.append, qos_profile_sensor_data)
    node.create_subscription(PointCloud2, '/lite3/lidar/points', clouds.append, qos_profile_sensor_data)
    try:
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
            if len(scans) >= 21 and buffer.can_transform(
                    'odom', 'base_footprint', Time.from_msg(scans[-3].header.stamp)):
                break
        assert len(scans) >= 21, '30秒内未收到足够扫描：检查仿真播放、桥接与QoS'
        scan = scans[-3]  # 给运动节点时间发布同一时刻的TF。
        assert scan.header.frame_id == 'base_footprint', scan.header.frame_id
        assert len(scan.ranges) == 720, len(scan.ranges)
        assert abs(scan.range_min - 0.12) < 1e-5
        assert abs(scan.range_max - 12.0) < 1e-5
        assert abs(scan.angle_min + math.pi) < 1e-5
        assert abs(scan.angle_max - (math.pi - scan.angle_increment)) < 1e-5
        assert clouds and clouds[-1].width * clouds[-1].height == 720*31
        assert all(not math.isnan(r) and r >= scan.range_min - 1e-4
                   and (math.isinf(r) or r <= scan.range_max + 1e-4)
                   for r in scan.ranges), '出现非法距离'
        hits = [r for r in scan.ranges if math.isfinite(r)]
        assert hits, '没有有效回波：检查场景可见几何与传感器渲染日志'
        transform = buffer.lookup_transform(
            'odom', 'base_footprint', Time.from_msg(scan.header.stamp))
        mount = buffer.lookup_transform('TORSO', 'lidar_link', Time())
        assert abs(mount.transform.translation.z - 0.15) < 1e-6
        stamps = [s.header.stamp.sec + s.header.stamp.nanosec * 1e-9
                  for s in scans]
        assert all(b > a for a, b in zip(stamps, stamps[1:])), '扫描时间未递增'
        rate = (len(stamps) - 1) / (stamps[-1] - stamps[0])
        assert 9.5 <= rate <= 10.5, f'仿真时间扫描接收频率异常：{rate}'
        print(json.dumps({
            'passed': True, 'frame': scan.header.frame_id,
            'samples': len(scan.ranges), 'finite_hits': len(hits),
            'nearest_hit_m': min(hits), 'sim_receiving_rate_hz': rate,
            'scan_stamp_tf_available': True,
            'projection_height_in_odom_m': transform.transform.translation.z,
        }, ensure_ascii=False, indent=2))
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
