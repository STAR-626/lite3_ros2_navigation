#!/usr/bin/env python3
"""启动阶段配置已有节点，使用伪终端准备并监管现有 RL 程序。

不训练或修改策略，不发布行走速度或导航目标。就绪后销毁临时 ROS 节点。
"""

import argparse
import errno
import json
import math
import os
from pathlib import Path
import pty
import re
import select
import signal
import subprocess
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from rclpy.signals import SignalHandlerOptions
from lifecycle_msgs.msg import State, Transition
from lifecycle_msgs.srv import ChangeState, GetState
from nav_msgs.msg import Odometry
from sensor_msgs.msg import JointState, PointCloud2
from rosgraph_msgs.msg import Clock
from std_srvs.srv import SetBool


class RLProcess:
    def __init__(self, directory, log_path):
        master, slave = pty.openpty()
        self.master = master
        self.log = open(log_path, 'ab', buffering=0)
        self.tail = ''
        self.pending = ''
        try:
            self.process = subprocess.Popen([str(Path(directory) / 'build' / 'rl_deploy'), '--ros-velocity'],
                                            cwd=Path(directory) / 'build', stdin=slave,
                                            stdout=slave, stderr=slave, start_new_session=True)
        except BaseException:
            os.close(master)
            self.log.close()
            raise
        finally:
            os.close(slave)

    def pump(self):
        if select.select([self.master], [], [], 0)[0]:
            try:
                data = os.read(self.master, 65536)
            except OSError as error:
                if error.errno != errno.EIO:
                    raise
                data = b''
            self.log.write(data)
            text = data.decode('utf-8', errors='replace')
            self.tail = (self.tail + text)[-65536:]
            lines = (self.pending + text).split('\n')
            self.pending = lines.pop()
            for line in lines:
                if any(token in line for token in ('--->', '[ONNX ENTER]', 'Policy command',
                                                   'Error', 'failed', 'startup failed')):
                    print('[RL] ' + line.rstrip(), flush=True)
            if re.search(r'\bnan\b|Error binding socket|Cannot bind|RL startup failed', self.tail,
                         flags=re.IGNORECASE):
                raise RuntimeError('RL 输出异常，详情见 rl-deploy.log')
        if self.process.poll() is not None:
            raise RuntimeError(f'RL 程序已退出，返回值 {self.process.returncode}，详情见 rl-deploy.log')

    def key(self, value):
        os.write(self.master, value.encode('ascii'))

    def close(self):
        if self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=3)
        os.close(self.master)
        self.log.close()


class Startup:
    def __init__(self, args):
        self.args = args
        self.deadline = time.monotonic() + args.timeout
        self.stopping = False
        self.rl = None
        self.node = Node('lite3_startup')
        self.odom_time = self.joints_time = self.cloud_time = 0.0
        self.sim_time = 0.0
        self.last_sim_change = 0.0
        self.node.create_subscription(Odometry, '/odom', self.odom, 10)
        self.node.create_subscription(JointState, '/joint_states', self.joints, 10)
        self.node.create_subscription(Clock, '/clock', self.clock,
                                      QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT))
        self.node.create_subscription(PointCloud2, '/lite3/perception/obstacles', self.cloud,
                                      QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT))
        self.stop_client = self.node.create_client(SetBool, '/lite3/set_stop')

    def odom(self, message):
        p, q = message.pose.pose.position, message.pose.pose.orientation
        values = (p.x, p.y, p.z, q.x, q.y, q.z, q.w)
        if all(math.isfinite(value) for value in values) and sum(v*v for v in values[3:]) > 0.5:
            self.odom_time = time.monotonic()

    def joints(self, message):
        if len(message.position) == 12 and all(math.isfinite(x) for x in message.position):
            self.joints_time = time.monotonic()

    def cloud(self, message):
        if (message.header.frame_id == 'lidar_link' and message.point_step >= 12
                and len(message.data) == message.row_step * message.height
                and {'x', 'y', 'z'}.issubset({field.name for field in message.fields})):
            self.cloud_time = time.monotonic()

    def clock(self, message):
        current = message.clock.sec + message.clock.nanosec / 1e9
        if current > self.sim_time:
            self.last_sim_change = time.monotonic()
        self.sim_time = current

    def tick(self):
        if self.stopping:
            raise InterruptedError('收到退出请求')
        if time.monotonic() >= self.deadline:
            raise TimeoutError('启动准备超时，请查看 Gazebo、桥接和 RL 日志')
        rclpy.spin_once(self.node, timeout_sec=0.03)
        if self.rl:
            self.rl.pump()

    def wait(self, condition, description):
        print('[Lite3 startup] ' + description, flush=True)
        while not condition():
            self.tick()

    def request(self, client, request):
        self.wait(client.service_is_ready, '等待 ' + client.srv_name)
        future = client.call_async(request)
        self.wait(future.done, '等待服务响应 ' + client.srv_name)
        response = future.result()
        if response is None:
            raise RuntimeError('服务没有返回结果：' + client.srv_name)
        return response

    def lock(self, value):
        response = self.request(self.stop_client, SetBool.Request(data=value))
        if not response.success:
            raise RuntimeError('运动停止服务拒绝请求：' + response.message)

    def activate(self, name):
        change = self.node.create_client(ChangeState, '/' + name + '/change_state')
        get = self.node.create_client(GetState, '/' + name + '/get_state')
        try:
            state = self.request(get, GetState.Request()).current_state.id
            if state != State.PRIMARY_STATE_UNCONFIGURED:
                raise RuntimeError(name + ' 已由其他启动入口配置，请先退出旧节点')
            for transition, expected in ((Transition.TRANSITION_CONFIGURE, State.PRIMARY_STATE_INACTIVE),
                                         (Transition.TRANSITION_ACTIVATE, State.PRIMARY_STATE_ACTIVE)):
                request = ChangeState.Request()
                request.transition.id = transition
                if not self.request(change, request).success:
                    raise RuntimeError(name + ' 生命周期转换失败，请看该节点日志')
                if self.request(get, GetState.Request()).current_state.id != expected:
                    raise RuntimeError(name + ' 未进入预期状态')
            print('[Lite3 startup] ' + name + ' 已激活', flush=True)
        finally:
            self.node.destroy_client(change)
            self.node.destroy_client(get)

    def set_gazebo_mode(self, mode):
        result = subprocess.run(['gz', 'topic', '-t', '/lite3/control_mode', '-m', 'gz.msgs.StringMsg',
                                 '-p', f'data: "{mode}"'], capture_output=True, text=True, timeout=5)
        if result.returncode:
            raise RuntimeError('Gazebo 模式请求失败：' + result.stderr)

    def prepare(self):
        self.lock(True)
        self.wait(lambda: min(self.odom_time, self.joints_time, self.last_sim_change, self.cloud_time) > time.monotonic() - 1,
                  '等待 Gazebo 的新鲜位置、12 个关节、运行中的时钟和三维感知输出')
        for name in ('map_server', 'planner_server', 'controller_server'):
            self.activate(name)
        self.rl = RLProcess(self.args.rl_dir, self.args.rl_log)
        self.wait(lambda: 'Waiting for stand up' in self.rl.tail, '等待 RL 初始化')
        self.rl.key('z')
        self.wait(lambda: re.search(r'idle_state\s*-+>\s*standup_state', self.rl.tail), '请求 RL 站立')
        # 收到站立状态反馈后再发送 c；RL 自身会等站立轨迹完成才进入策略。
        started = self.sim_time
        self.wait(lambda: self.sim_time > started + 0.1, '等待站立状态生效')
        self.rl.key('c')
        self.wait(lambda: '[ONNX ENTER] PolicyRunner entered:' in self.rl.tail, '等待站立完成并进入 RL 策略')
        requested = time.monotonic()
        last_request = 0.0

        def external_confirmed():
            nonlocal last_request
            now = time.monotonic()
            if now - last_request > 0.7:
                self.set_gazebo_mode('external')
                last_request = now
            try:
                state = json.loads(Path(self.args.mode_file).read_text())
            except (OSError, ValueError):
                return False
            return state['mode'] == 'external' and state['received'] >= requested

        self.wait(external_confirmed, '等待实际 Gazebo 插件确认 external 接管')
        self.lock(False)
        print('[Lite3 startup] READY：准备完成，等待用户发送目标。没有自动导航。', flush=True)

    def close(self):
        if self.rl:
            try:
                self.set_gazebo_mode('stand')
            except (OSError, RuntimeError, subprocess.TimeoutExpired):
                pass
            self.rl.close()
        self.node.destroy_node()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rl-dir', required=True)
    parser.add_argument('--mode-file', required=True)
    parser.add_argument('--rl-log', required=True)
    parser.add_argument('--timeout', type=float, default=120)
    args = parser.parse_args()
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error('--timeout 必须是正的有限秒数')
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    startup = Startup(args)
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: setattr(startup, 'stopping', True))
    try:
        startup.prepare()
        # 运行阶段只监管子进程，不保留额外的 ROS 功能节点。
        startup.node.destroy_node()
        startup.node = None
        rclpy.shutdown()
        while not startup.stopping:
            startup.rl.pump()
            time.sleep(0.05)
        return 0
    except InterruptedError:
        return 0
    except Exception as error:
        print('[Lite3 startup] ERROR：' + str(error), flush=True)
        return 1
    finally:
        # close 中只回收由本进程启动的 RL，不影响用户其他进程。
        if startup.node is None:
            if startup.rl:
                try:
                    startup.set_gazebo_mode('stand')
                except (OSError, RuntimeError, subprocess.TimeoutExpired):
                    pass
                startup.rl.close()
        else:
            startup.close()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
