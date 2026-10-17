#!/usr/bin/env python3
"""Submit a terminal goal to the existing NavigateTask action (angle in degrees)."""
import argparse
import math
import sys

import rclpy
from rclpy.action import ActionClient
from lite3_interfaces.action import NavigateTask


def parse_goal(argv):
    parser = argparse.ArgumentParser(description='导航到 X Y 角度；位置单位米，角度默认度数。')
    parser.add_argument('x')
    parser.add_argument('y')
    parser.add_argument('angle')
    parser.add_argument('--radians', action='store_true', help='角度改用弧度[-pi,pi]')
    args = parser.parse_args(argv)
    values = []
    for name in ('x', 'y', 'angle'):
        try:
            value = float(getattr(args, name))
        except ValueError:
            raise ValueError(f'INVALID_GOAL (3)：{name} 必须是数字') from None
        if not math.isfinite(value):
            raise ValueError(f'INVALID_GOAL (3)：{name} 不能是 NaN 或无穷大')
        values.append(value)
    limit = math.pi if args.radians else 180.0
    if abs(values[2]) > limit:
        raise ValueError(f'INVALID_GOAL (3)：角度应在 [{-limit:g},{limit:g}] 范围内')
    yaw = values[2] if args.radians else math.radians(values[2])
    return NavigateTask.Goal(goal_x=values[0], goal_y=values[1], goal_yaw=yaw)


def main(argv=None):
    try:
        goal = parse_goal(sys.argv[1:] if argv is None else argv)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 3
    rclpy.init(args=[])
    node = rclpy.create_node('lite3_terminal_goal')
    client = ActionClient(node, NavigateTask, '/navigate_task')
    handle = None
    try:
        if not client.wait_for_server(timeout_sec=5.0):
            print('SYSTEM_ERROR (8)：找不到任务节点，请先启动整套系统', file=sys.stderr)
            return 8
        def feedback(message):
            print(f'{message.feedback.phase}：剩余距离 '
                  f'{message.feedback.remaining_distance:.2f} m', flush=True)
        future = client.send_goal_async(goal, feedback_callback=feedback)
        rclpy.spin_until_future_complete(node, future, timeout_sec=5.0)
        if not future.done():
            print('SYSTEM_ERROR (8)：提交响应超时，请检查导航状态；不要重复提交', file=sys.stderr)
            return 8
        handle = future.result()
        if not handle.accepted:
            print('BUSY_OR_FAULT：任务被拒绝，请查看启动终端或 /lite3/navigation_status')
            return 8
        result = handle.get_result_async()
        rclpy.spin_until_future_complete(node, result)
        response = result.result().result
        print(f'RESULT {response.result_code}：{response.message}', flush=True)
        return response.result_code
    except KeyboardInterrupt:
        print('客户端已退出；这不代表任务已取消。可关闭导航总开关以取消并停止。')
        return 130
    finally:
        client.destroy()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    sys.exit(main())
