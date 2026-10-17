#!/usr/bin/env python3
"""隔离域196：用真实Nav2控制器验证轮廓，不启动Gazebo/RL/运动节点。

合成静态地图只用于验证横向空隙和前向/转向碰撞检查，不代表真实行走验收。
"""
import copy
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time

import rclpy
from geometry_msgs.msg import PoseStamped, TransformStamped, Twist
from lifecycle_msgs.srv import ChangeState
from nav_msgs.msg import OccupancyGrid, Odometry, Path as RosPath
from nav2_msgs.action import FollowPath
from rclpy.action import ActionClient
from rclpy.qos import QoSProfile, DurabilityPolicy
from tf2_ros import TransformBroadcaster
import yaml


def main():
    assert os.environ.get('ROS_DOMAIN_ID') == '196', '只能在独立ROS域196执行'
    config_path = Path(__file__).resolve().parents[1] / 'config/controller.yaml'
    config = yaml.safe_load(config_path.read_text())
    rclpy.init()
    node = rclpy.create_node('navigation_footprint_fixture')
    broadcaster = TransformBroadcaster(node)
    odom_pub = node.create_publisher(Odometry, '/odom', 10)
    map_pub = node.create_publisher(OccupancyGrid, '/map',
        QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))
    yaw = 0.0
    processes = []
    resources = []
    summary = []

    def tick():
        stamp = node.get_clock().now().to_msg()
        tf = TransformStamped()
        tf.header.stamp = stamp
        tf.header.frame_id = 'odom'
        tf.child_frame_id = 'base_footprint'
        tf.transform.rotation.z = math.sin(yaw / 2)
        tf.transform.rotation.w = math.cos(yaw / 2)
        broadcaster.sendTransform(tf)
        odom = Odometry()
        odom.header = tf.header
        odom.child_frame_id = tf.child_frame_id
        odom.pose.pose.orientation = tf.transform.rotation
        odom_pub.publish(odom)

    timer = node.create_timer(.02, tick)

    def wait(condition, seconds=10):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            rclpy.spin_once(node, timeout_sec=.02)
            if condition():
                return
        for resource in resources:
            if not resource.closed:
                resource.flush()
                print(Path(resource.name).read_text(errors='replace')[-4500:], flush=True)
        raise AssertionError('隔离测试等待超时')

    def result(future):
        wait(future.done, 15)
        return future.result()

    def transition(namespace, state):
        client = node.create_client(ChangeState, namespace + '/controller_server/change_state')
        wait(client.service_is_ready)
        req = ChangeState.Request()
        req.transition.id = state
        assert result(client.call_async(req)).success
        node.destroy_client(client)

    def make_map(front, corridor_width):
        grid = OccupancyGrid()
        grid.header.frame_id = 'odom'
        grid.header.stamp = node.get_clock().now().to_msg()
        grid.info.resolution = .02
        grid.info.width = grid.info.height = 300
        grid.info.origin.position.x = grid.info.origin.position.y = -3.
        grid.info.origin.orientation.w = 1.
        data = []
        for iy in range(300):
            yy = -3 + (iy + .5) * .02
            for ix in range(300):
                xx = -3 + (ix + .5) * .02
                wall = abs(yy) >= corridor_width / 2
                box = front and .45 <= xx <= .60 and abs(yy) < .15
                data.append(100 if wall or box else 0)
        grid.data = data
        return grid

    try:
        with tempfile.TemporaryDirectory(prefix='lite3-footprint-') as temp:
            cases = [('old_circle', 'circle', False, 0., .70, False),
                     ('previous_rectangle_30cm', 'previous', False, 0., .50, False),
                     ('rectangle_corridor', 'current', False, 0., .50, True),
                     ('rectangle_too_narrow', 'current', False, 0., .38, False),
                     ('rectangle_front_blocked', 'current', True, 0., .50, False),
                     ('rectangle_sideways_blocked', 'current', False, math.pi / 2, .50, False)]
            for label, shape, front, yaw_value, corridor_width, should_move in cases:
                yaw = yaw_value
                namespace = '/footprint_' + label
                params = copy.deepcopy(config)
                ctrl = params['controller_server']['ros__parameters']
                local = params['local_costmap']['local_costmap']['ros__parameters']
                ctrl['use_sim_time'] = local['use_sim_time'] = False
                local['plugins'] = ['static_layer', 'inflation_layer']
                local.pop('voxel_layer')
                if shape == 'circle':
                    local.pop('footprint')
                    local['footprint_padding'] = .01
                    local['robot_radius'] = .4
                elif shape == 'previous':
                    local['footprint'] = '[[.40,.28],[-.40,.28],[-.40,-.28],[.40,-.28]]'
                    local['footprint_padding'] = .02
                document = {namespace + '/controller_server': params['controller_server'],
                    namespace + '/local_costmap/local_costmap': {'ros__parameters': local}}
                filename = Path(temp) / (label + '.yaml')
                filename.write_text(yaml.safe_dump(document))
                logfile = Path(temp) / (label + '.log')
                output = logfile.open('w')
                resources.append(output)
                velocity = []
                costmap = []
                footprint = []
                from geometry_msgs.msg import PolygonStamped
                sub = node.create_subscription(Twist, namespace + '/cmd_vel',
                    lambda m: velocity.append(m.linear.x), 10)
                submap = node.create_subscription(OccupancyGrid,
                    namespace + '/local_costmap/costmap', lambda m: costmap.append(m), 1)
                subfoot = node.create_subscription(PolygonStamped,
                    namespace + '/local_costmap/published_footprint',
                    lambda m: footprint.append(m), 1)
                proc = subprocess.Popen(['ros2', 'run', 'nav2_controller', 'controller_server',
                    '--ros-args', '--params-file', str(filename), '-r', '__ns:=' + namespace],
                    stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
                processes.append(proc)
                transition(namespace, 1)
                # 保持同一地图发布器及TF；每个独立命名空间仅接收自己的控制任务。
                map_pub.publish(make_map(front, corridor_width))
                started = time.monotonic()
                wait(lambda: time.monotonic() - started > 1.5)
                transition(namespace, 3)
                wait(lambda: costmap and footprint)
                client = ActionClient(node, FollowPath, namespace + '/follow_path')
                wait(client.server_is_ready)
                goal = FollowPath.Goal()
                goal.controller_id = 'FollowPath'
                goal.goal_checker_id = 'goal_checker'
                goal.path = RosPath()
                goal.path.header.frame_id = 'odom'
                goal.path.header.stamp = node.get_clock().now().to_msg()
                # 各姿态沿自身正前方给路径，避免用原地转向掩盖前向检查。
                for i in range(81):
                    pose = PoseStamped()
                    pose.header = goal.path.header
                    pose.pose.position.x = i * .025 * math.cos(yaw)
                    pose.pose.position.y = i * .025 * math.sin(yaw)
                    pose.pose.orientation.z = math.sin(yaw / 2)
                    pose.pose.orientation.w = math.cos(yaw / 2)
                    goal.path.poses.append(pose)
                handle = result(client.send_goal_async(goal))
                assert handle.accepted
                outcome = handle.get_result_async()
                velocity.clear()
                started = time.monotonic()
                wait(lambda: outcome.done() or time.monotonic() - started > 1.2)
                moving = any(v > .1 for v in velocity)
                if not outcome.done():
                    result(handle.cancel_goal_async())
                reply = result(outcome)
                if should_move:
                    assert moving and reply.status == 5, (label, velocity, reply)
                else:
                    assert not moving and reply.status == 6, (label, velocity, reply)
                    assert reply.result.error_code == 104, (label, reply)
                points = [(p.x, p.y) for p in footprint[-1].polygon.points]
                summary.append({'case': label, 'corridor_width_m': corridor_width,
                    'positive_velocity': moving,
                    'action_status': reply.status, 'error_code': reply.result.error_code,
                    'published_footprint': points})
                print(json.dumps(summary[-1]), flush=True)
                client.destroy()
                for subscription in (sub, submap, subfoot):
                    node.destroy_subscription(subscription)
                os.killpg(proc.pid, signal.SIGINT)
                try:
                    proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGTERM)
                    proc.wait(timeout=5)
                output.close()
            print('PASS: 0.50m通道旧30cm矩形阻挡、新20cm矩形允许前进；过窄、前方障碍及朝向不合仍阻挡。')
    finally:
        for proc in processes:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGTERM)
                proc.wait(timeout=5)
        for resource in resources:
            resource.close()
        node.destroy_timer(timer)
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
