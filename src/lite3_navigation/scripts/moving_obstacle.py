#!/usr/bin/env python3
"""加入一个带碰撞体的箱子，使其匀速移动一段实际时间，然后停车。"""
import argparse
import re
import math
from pathlib import Path
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET

from ament_index_python.packages import get_package_share_directory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--x', type=float, default=-1.8, help='起点world X，米')
    parser.add_argument('--y', type=float, default=-4.6, help='起点world Y，米')
    parser.add_argument('--vx', type=float, default=0., help='箱子X速度，米/秒（初始朝向为0）')
    parser.add_argument('--vy', type=float, default=.18, help='箱子Y速度，米/秒')
    parser.add_argument('--seconds', type=float, default=8., help='持续实际秒数；暂停仿真仍计时')
    parser.add_argument('--remove', action='store_true', help='停车后移除本次创建的箱子')
    args = parser.parse_args()
    values = [args.x, args.y, args.vx, args.vy, args.seconds]
    if not all(math.isfinite(v) for v in values) or not 0 < args.seconds <= 120:
        parser.error('输入必须为有限数字，seconds在(0,120]内')
    if abs(args.vx) > .5 or abs(args.vy) > .5:
        parser.error('当前验收工具每轴限速0.5米/秒，请从低速开始')

    def service(operation, kind, request):
        result = subprocess.run(['gz', 'service', '-s', '/world/large_warehouse/' + operation,
            '--reqtype', kind, '--reptype', 'gz.msgs.Boolean', '--timeout', '4000', '--req', request],
            capture_output=True, text=True, timeout=6)
        if result.returncode or 'data: true' not in result.stdout:
            raise RuntimeError('Gazebo操作失败；确认已启动仿真且没有同名箱子：' + result.stdout + result.stderr)

    def velocity(vx, vy):
        subprocess.run(['gz', 'topic', '-t', '/lite3/dynamic_box/cmd_vel', '-m', 'gz.msgs.Twist',
            '-p', f'linear: {{x: {vx}, y: {vy}}}'], check=True, timeout=5)

    # Gazebo create's Boolean acknowledges a queued request, not unique model
    # ownership. A duplicate can return true while retaining the old model.
    # Query the actual world first; never send velocity to an existing box.
    snapshot = subprocess.run(['gz', 'service', '-s', '/world/large_warehouse/scene/info',
        '--reqtype', 'gz.msgs.Empty', '--reptype', 'gz.msgs.Scene',
        '--timeout', '4000', '--req', ''], capture_output=True, text=True, timeout=6)
    if snapshot.returncode or not snapshot.stdout.strip():
        parser.error('无法查询当前Gazebo world，未创建或移动任何箱子；确认仿真已启动')
    if re.search(r'\bname:\s*"lite3_dynamic_box"', snapshot.stdout):
        parser.error('lite3_dynamic_box已存在，拒绝覆盖或控制它；先明确移除已有测试箱子')

    created = False
    try:
        with tempfile.TemporaryDirectory(prefix='lite3-dynamic-box-') as directory:
            model = ET.parse(Path(get_package_share_directory('lite3_gazebo'))/'worlds/lite3_dynamic_box.sdf')
            model.getroot().find('model/pose').text = f'{args.x} {args.y} 0.205 0 0 0'
            filename = Path(directory)/'box.sdf'
            model.write(filename, encoding='utf-8', xml_declaration=True)
            service('create', 'gz.msgs.EntityFactory', f'sdf_filename: "{filename}"')
            created = True
            # 给新增模型的Gazebo速度订阅者留出发现时间。
            time.sleep(.5)
            velocity(args.vx, args.vy)
            print(f'箱子已加入，速度({args.vx}, {args.vy})m/s，持续{args.seconds}实际秒。Ctrl+C提前停车。', flush=True)
            deadline = time.monotonic()+args.seconds
            while time.monotonic() < deadline:
                time.sleep(min(.1, max(0., deadline-time.monotonic())))
    except KeyboardInterrupt:
        print('收到退出请求，正在停止箱子。', flush=True)
    finally:
        if created:
            velocity(0., 0.)
            print('箱子已发送零速度；机器人导航任务不受此命令直接控制。', flush=True)
            if args.remove:
                service('remove', 'gz.msgs.Entity', 'name: "lite3_dynamic_box", type: MODEL')


if __name__ == '__main__':
    main()
