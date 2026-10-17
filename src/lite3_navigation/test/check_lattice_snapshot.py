#!/usr/bin/env python3
"""Domain204: real NavFn vs Lattice on a saved live obstacle map, no robot commands."""
import argparse
import copy
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time

import numpy as np
import rclpy
from geometry_msgs.msg import PoseStamped, TransformStamped
from lifecycle_msgs.srv import ChangeState
from nav_msgs.msg import OccupancyGrid
from nav2_msgs.action import ComputePathToPose
from rclpy.action import ActionClient
from rclpy.qos import QoSProfile, DurabilityPolicy
from rosidl_runtime_py.convert import message_to_ordereddict
from tf2_ros import StaticTransformBroadcaster
from ament_index_python.packages import get_package_share_directory
import yaml


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('--clear-approach', action='store_true', help='同一快照中从狭口前的开阔位置检查提前绕路')
    parser.add_argument('--fixture', choices=['snapshot','open','warehouse','corner'], default='snapshot')
    parser.add_argument('--grid-json', type=Path, help='以保存的OccupancyGrid替代快照障碍数据')
    parser.add_argument('--expected-error', type=int, help='断言Lattice返回码，0表示成功')
    parser.add_argument('--penalty-check', action='store_true', help='开阔地图验证失败路段软代价会改变路线')
    parser.add_argument('--start', type=float, nargs=3, metavar=('X','Y','YAW_RAD'))
    parser.add_argument('--reverse', action='store_true')
    parser.add_argument('--goal-x', type=float, default=-4.137228)
    parser.add_argument('--goal-y', type=float, default=-3.516892)
    parser.add_argument('--goal-yaw', type=float, default=0., help='弧度')
    args = parser.parse_args()
    assert os.environ.get('ROS_DOMAIN_ID') == '204'
    source = args.snapshot
    snapshot = json.loads((source/'snapshot.json').read_text())
    grid = np.load(source/'global_costmap_costmap.npy')
    meta = snapshot['/global_costmap/costmap']['info']
    actual = snapshot['/odom']['pose']['pose']
    if args.clear_approach:
        actual = copy.deepcopy(actual)
        actual['position'].update(x=1.5, y=1.0)
        actual['orientation'].update(x=0., y=0., z=1., w=0.)
    root = Path(__file__).resolve().parents[3]
    if args.fixture != 'snapshot':
        actual = copy.deepcopy(actual)
        actual['position'].update(x=-4., y=-4.)
        actual['orientation'].update(x=0., y=0., z=0., w=1.)
        grid[:] = 0
        if args.fixture == 'corner':
            yy,xx=np.indices(grid.shape)
            xx=meta['origin']['position']['x']+(xx+.5)*meta['resolution']
            yy=meta['origin']['position']['y']+(yy+.5)*meta['resolution']
            corridor=((xx>=-4.6)&(xx<=.25)&(np.abs(yy+4.)<=.25))|((np.abs(xx)<=.25)&(yy>=-4.25)&(yy<=.6))
            grid=np.where(corridor,0,100)
        if args.fixture == 'warehouse':
            from PIL import Image
            pixels = np.flipud(np.array(Image.open(root/'src/lite3_gazebo/maps/large_warehouse.pgm')))
            grid = np.where(pixels < 89, 100, np.where(pixels > 205, 0, -1))
    if args.start:
        sx,sy,st=args.start
        actual=copy.deepcopy(actual)
        actual['position'].update(x=sx,y=sy)
        actual['orientation'].update(x=0.,y=0.,z=math.sin(st/2),w=math.cos(st/2))
    if args.grid_json:
        live = json.loads(args.grid_json.read_text())
        meta = live['info']
        grid = np.array(live['data']).reshape(meta['height'],meta['width'])
    output = Path(tempfile.mkdtemp(prefix='lite3-lattice-snapshot-'))
    rclpy.init()
    node = rclpy.create_node('lattice_snapshot_fixture')
    publisher = node.create_publisher(OccupancyGrid, '/map',
        QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))
    tf = StaticTransformBroadcaster(node)
    t = TransformStamped()
    t.header.frame_id = 'map'; t.child_frame_id = 'base_footprint'
    t.transform.translation.x = actual['position']['x']; t.transform.translation.y = actual['position']['y']
    for key in ['x', 'y', 'z', 'w']:
        setattr(t.transform.rotation, key, actual['orientation'][key])
    tf.sendTransform(t)
    message = OccupancyGrid()
    message.header.frame_id = 'map'
    message.info.width, message.info.height = meta['width'], meta['height']
    message.info.resolution = meta['resolution']
    message.info.origin.position.x = meta['origin']['position']['x']
    message.info.origin.position.y = meta['origin']['position']['y']
    message.info.origin.orientation.w = 1.
    # Rebuild inflation from measured lethal cells, don't turn old inflation into walls.
    message.data = np.where(grid < 0, -1, np.where(grid == 100, 100, 0)).astype(np.int8).ravel().tolist()
    publisher.publish(message)
    results = []
    current = None

    def wait(predicate, seconds=15):
        end = time.monotonic()+seconds
        while time.monotonic() < end:
            rclpy.spin_once(node, timeout_sec=.02)
            if predicate(): return
        raise AssertionError('Snapshot timeout: '+str(output))

    def result(future, seconds=15):
        wait(future.done, seconds)
        return future.result()

    try:
        for profile in ['navfn', 'lattice']:
            filename = 'planner_navfn.yaml' if profile == 'navfn' else 'planner.yaml'
            cfg = yaml.safe_load((root/'src/lite3_navigation/config'/filename).read_text())
            cp = cfg['planner_server']['ros__parameters']
            cm = cfg['global_costmap']['global_costmap']['ros__parameters']
            cp['use_sim_time'] = cm['use_sim_time'] = False
            cm['plugins'] = ['static_layer', 'inflation_layer']
            if profile == 'lattice':
                if args.reverse: cp['GridBased']['allow_reverse_expansion'] = True
                if args.penalty_check:
                    cm['plugins'].insert(1, 'route_penalty_layer')
                cp['GridBased']['lattice_filepath'] = str(Path(get_package_share_directory('nav2_smac_planner'))/
                    'sample_primitives/5cm_resolution/0.5m_turning_radius/diff/output.json')
            f = output/(profile+'.yaml'); f.write_text(yaml.safe_dump(cfg))
            log = (output/(profile+'.log')).open('w')
            current = subprocess.Popen(['ros2', 'run', 'nav2_planner', 'planner_server',
                '--ros-args', '--params-file', str(f)], stdout=log, stderr=subprocess.STDOUT,
                start_new_session=True)
            client = node.create_client(ChangeState, '/planner_server/change_state')
            wait(client.service_is_ready)
            for state in (1, 3):
                request = ChangeState.Request(); request.transition.id = state
                assert result(client.call_async(request)).success
            action = ActionClient(node, ComputePathToPose, '/compute_path_to_pose')
            wait(action.server_is_ready)
            started = time.monotonic()
            wait(lambda: time.monotonic()-started > .6)
            goal = ComputePathToPose.Goal()
            goal.planner_id = 'GridBased'; goal.use_start = True
            for dest, x, y, q in [(goal.start, actual['position']['x'], actual['position']['y'], actual['orientation']),
                                (goal.goal, args.goal_x, args.goal_y, {'x':0.,'y':0.,'z':math.sin(args.goal_yaw/2),'w':math.cos(args.goal_yaw/2)})]:
                dest.header.frame_id = 'map'; dest.pose.position.x = x; dest.pose.position.y = y
                for key in ['x', 'y', 'z', 'w']: setattr(dest.pose.orientation, key, q[key])
            handle = result(action.send_goal_async(goal)); assert handle.accepted
            reply = result(handle.get_result_async())
            document = {'profile':profile, 'status':reply.status, 'result':message_to_ordereddict(reply.result)}
            (output/(profile+'_result.json')).write_text(json.dumps(document, indent=2))
            print(profile, reply.status, reply.result.error_code, reply.result.error_msg,
                  'points', len(reply.result.path.poses), flush=True)
            if profile == 'lattice' and args.expected_error is not None:
                assert reply.result.error_code == args.expected_error, document
            results.append({'profile':profile, 'status':reply.status, 'error':reply.result.error_code,
                            'points':len(reply.result.path.poses)})
            if profile == 'lattice' and args.penalty_check:
                from nav_msgs.msg import Path as RosPath
                hint_pub = node.create_publisher(RosPath, '/lite3/avoidance/failed_route', QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))
                baseline = reply.result.path
                assert baseline.poses
                hints = RosPath(); hints.header = baseline.header
                n = len(baseline.poses)
                hints.poses = baseline.poses[n//3:n//3+max(2,n//12)]
                hint_pub.publish(hints)
                started = time.monotonic(); wait(lambda: time.monotonic()-started > 1.5)
                second_handle = result(action.send_goal_async(goal))
                second = result(second_handle.get_result_async())
                assert second.result.error_code == 0, second
                old = np.array([[p.pose.position.x,p.pose.position.y] for p in baseline.poses])
                new = np.array([[p.pose.position.x,p.pose.position.y] for p in second.result.path.poses])
                separation = float(np.max(np.min(np.linalg.norm(new[:,None,:]-old[None,:,:],axis=2),axis=1)))
                assert separation > .10, separation
                results.append({'soft_preference_changes_route': True, 'maximum_separation_m': separation})
                (output/'preferred_result.json').write_text(json.dumps(message_to_ordereddict(second.result)))
                hint_pub.publish(RosPath())
                node.destroy_publisher(hint_pub)
            action.destroy(); node.destroy_client(client)
            os.killpg(current.pid, signal.SIGINT); current.wait(timeout=10)
            current = None; log.close()
            started = time.monotonic(); wait(lambda: time.monotonic()-started > 1.)
        (output/'result.json').write_text(json.dumps(results, indent=2))
        print('RESULT_DIRECTORY', output, flush=True)
    finally:
        if current and current.poll() is None:
            os.killpg(current.pid, signal.SIGTERM); current.wait(timeout=5)
        node.destroy_node(); rclpy.shutdown()


if __name__ == '__main__':
    main()
