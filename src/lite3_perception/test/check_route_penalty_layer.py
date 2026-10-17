#!/usr/bin/env python3
"""Domain206: real Nav2 layer, marking/movement/empty/expiry/TF/static preservation.

No Gazebo, RL, UDP, navigation goal or robot motion.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time

import rclpy
from geometry_msgs.msg import TransformStamped
from lifecycle_msgs.srv import ChangeState
from nav_msgs.msg import OccupancyGrid, Path as RosPath
from geometry_msgs.msg import PoseStamped
from rclpy.qos import QoSProfile, DurabilityPolicy, qos_profile_sensor_data
from sensor_msgs.msg import PointCloud2
from sensor_msgs_py import point_cloud2
from std_msgs.msg import Header
from tf2_ros import StaticTransformBroadcaster
import yaml


def main():
    assert os.environ.get('ROS_DOMAIN_ID') == '206'
    root = Path(__file__).resolve().parents[3]
    directory = Path(tempfile.mkdtemp(prefix='lite3-route-penalty-'))
    cfg = yaml.safe_load((root/'src/lite3_navigation/config/controller.yaml').read_text())
    cfg['controller_server']['ros__parameters']['use_sim_time'] = False
    local = cfg['local_costmap']['local_costmap']['ros__parameters']
    local.update(use_sim_time=False, update_frequency=10., publish_frequency=10.,
                 plugins=['static_layer', 'route_penalty_layer', 'inflation_layer'])
    local['route_penalty_layer'] = {'plugin': 'lite3_perception::RoutePenaltyLayer', 'timeout': .5, 'cost': 200, 'radius': .18}
    path = directory/'params.yaml'
    path.write_text(yaml.safe_dump(cfg))
    rclpy.init()
    node = rclpy.create_node('route_penalty_fixture')
    latest = []
    node.create_subscription(OccupancyGrid, '/local_costmap/costmap', latest.append, 1)
    cloud_pub = node.create_publisher(RosPath, '/lite3/avoidance/failed_route', QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))
    map_pub = node.create_publisher(OccupancyGrid, '/map',
        QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))
    broadcaster = StaticTransformBroadcaster(node)
    for parent, child, x in [('odom', 'base_footprint', 0.), ('odom', 'forecast_test_frame', .3)]:
        t = TransformStamped()
        t.header.stamp = node.get_clock().now().to_msg()
        t.header.frame_id, t.child_frame_id = parent, child
        t.transform.translation.x = x
        t.transform.rotation.w = 1.
        broadcaster.sendTransform(t)
    message = OccupancyGrid()
    message.header.frame_id = 'odom'
    message.info.resolution = .05
    message.info.width = message.info.height = 120
    message.info.origin.position.x = message.info.origin.position.y = -3.
    message.info.origin.orientation.w = 1.
    message.data = [0]*14400
    message.data[29*120+29] = 100  # Static cell at(-1.525,-1.525), away from forecast halo.
    map_pub.publish(message)
    log = (directory/'controller.log').open('w')
    proc = subprocess.Popen(['ros2', 'run', 'nav2_controller', 'controller_server',
        '--ros-args', '--params-file', str(path)], stdout=log, stderr=subprocess.STDOUT,
        start_new_session=True)
    checks = []

    def wait(predicate, timeout=12):
        end = time.monotonic()+timeout
        while time.monotonic() < end:
            rclpy.spin_once(node, timeout_sec=.02)
            if predicate():
                return
        raise AssertionError((directory/'controller.log').read_text()[-3000:])

    def cost(x, y):
        if not latest:
            return -1
        grid = latest[-1]
        # Marked coordinates may fall on a floating-point cell boundary.
        return max(grid.data[
            int((y+dy-grid.info.origin.position.y)/grid.info.resolution)*grid.info.width+
            int((x+dx-grid.info.origin.position.x)/grid.info.resolution)]
            for dx in (-.03, 0, .03) for dy in (-.03, 0, .03))

    target = [(1., 0., .3)]  # TF +.3 -> odom x=1.
    publishing = True

    def publish():
        if publishing:
            path = RosPath()
            path.header.frame_id = 'odom'
            for x, y, z in target:
                pose = PoseStamped()
                pose.pose.position.x = x; pose.pose.position.y = y
                path.poses.append(pose)
            cloud_pub.publish(path)
    timer = node.create_timer(.05, publish)
    try:
        client = node.create_client(ChangeState, '/controller_server/change_state')
        wait(client.service_is_ready)
        for state in (1, 3):
            request = ChangeState.Request()
            request.transition.id = state
            future = client.call_async(request)
            wait(future.done)
            assert future.result().success
        wait(lambda: 0 < cost(1., 0.) < 99 and cost(-1.525, -1.525) == 100)
        checks.append('soft cost below collision threshold; static retained')
        target = [(1., 1., .3)]
        wait(lambda: 0 < cost(1., 1.) < 99 and cost(1., 0.) == 0)
        checks.append('moved preference clears previous cells')
        target = []
        wait(lambda: cost(1., 1.) == 0)
        checks.append('empty hint clears preference')
        target = [(1., 1., .3)]
        wait(lambda: 0 < cost(1., 1.) < 99)
        publishing = False
        wait(lambda: cost(1., 1.) == 0)
        assert cost(-1.525, -1.525) == 100
        checks.append('expired hint clears preference but retains static map')
        (directory/'result.json').write_text(json.dumps({'passed': True, 'checks': checks}, indent=2))
        print('PASS', checks, 'RESULT_FILE', directory/'result.json', flush=True)
    finally:
        node.destroy_timer(timer)
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGINT)
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGTERM)
                proc.wait(timeout=5)
        log.close()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
