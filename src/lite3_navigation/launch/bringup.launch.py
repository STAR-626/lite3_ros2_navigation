"""一条 launch 命令启动已完成的仓库导航系统。"""

import json
import os
from pathlib import Path
import socket
import sys
import time

from ament_index_python.packages import get_package_prefix, get_package_share_directory
from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, EmitEvent, ExecuteProcess,
                            IncludeLaunchDescription, LogInfo, OpaqueFunction,
                            RegisterEventHandler)
from launch.event_handlers import OnProcessExit, OnProcessIO
from launch.events import Shutdown
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch.logging import launch_config


def _start(context):
    navigation = get_package_share_directory('lite3_navigation')
    gazebo = get_package_share_directory('lite3_gazebo')
    profile = LaunchConfiguration('controller').perform(context).lower()
    if profile not in ('mppi', 'rpp'):
        raise RuntimeError('controller必须为mppi或rpp')
    if profile == 'mppi':
        get_package_prefix('nav2_mppi_controller')
    controller_config = 'controller_mppi.yaml' if profile == 'mppi' else 'controller.yaml'
    planner_profile = LaunchConfiguration('planner').perform(context).lower()
    if planner_profile not in ('lattice', 'navfn'):
        raise RuntimeError('planner必须为lattice或navfn')
    planner_parameters = [os.path.join(navigation, 'config',
        'planner.yaml' if planner_profile == 'lattice' else 'planner_navfn.yaml')]
    if planner_profile == 'lattice':
        primitives = os.path.join(get_package_share_directory('nav2_smac_planner'),
            'sample_primitives', '5cm_resolution', '0.5m_turning_radius',
            'omni' if profile == 'mppi' else 'diff', 'output.json')
        if not os.path.isfile(primitives):
            raise RuntimeError('缺少5cm导航运动集：' + primitives)
        planner_parameters.append({'GridBased.lattice_filepath': primitives,
                                   'GridBased.allow_reverse_expansion': profile == 'mppi'})
    rl_dir = Path(LaunchConfiguration('rl_dir').perform(context)).expanduser().resolve()
    executable = rl_dir / 'build' / 'rl_deploy'
    policy = rl_dir / 'policy' / 'ppo' / 'policy.onnx'
    if not executable.is_file() or not os.access(executable, os.X_OK) or not policy.is_file():
        raise RuntimeError(f'RL 程序或策略不存在：{executable} / {policy}。先按外部 RL 恢复说明构建。')
    # 不终止旧进程。发现端口占用时拒绝另起一套控制系统。
    for port in (20001, 30010, 30011):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            try:
                probe.bind(('127.0.0.1', port))
            except OSError as error:
                raise RuntimeError(f'UDP {port} 已占用，请先退出旧 Gazebo / RL / MuJoCo：{error}') from error

    # 旧地图或任务节点可能仍在运行，却没有占用 UDP；启动前检查同一 ROS 域。
    import rclpy
    from rclpy.context import Context
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.signals import SignalHandlerOptions
    probe_context = Context()
    rclpy.init(args=[], context=probe_context, signal_handler_options=SignalHandlerOptions.NO)
    probe_node = rclpy.create_node('lite3_bringup_probe', context=probe_context)
    executor = SingleThreadedExecutor(context=probe_context)
    executor.add_node(probe_node)
    try:
        deadline = time.monotonic() + 1.0
        conflicts = set()
        reserved = {'lite3_motion_node', 'mission_manager', 'map_server',
                    'planner_server', 'controller_server', 'ros_gz_bridge',
                    'robot_state_publisher', 'map_to_odom', 'lite3_startup',
                    'lite3_pointcloud_obstacles'}
        while time.monotonic() < deadline:
            executor.spin_once(timeout_sec=0.05)
            conflicts.update(reserved.intersection(probe_node.get_node_names()))
        if conflicts:
            raise RuntimeError('同一 ROS 域已有项目节点，请先关闭旧启动终端：' + ', '.join(sorted(conflicts)))
    finally:
        executor.remove_node(probe_node)
        executor.shutdown()
        probe_node.destroy_node()
        rclpy.shutdown(context=probe_context)

    log_dir = Path(launch_config.log_dir)
    mode_file = log_dir / 'lite3-control-mode.json'
    runtime = ExecuteProcess(
        cmd=[sys.executable, '-u', os.path.join(get_package_prefix('lite3_navigation'),
             'lib', 'lite3_navigation', 'bringup_runtime.py'),
             '--rl-dir', str(rl_dir), '--mode-file', str(mode_file),
             '--rl-log', str(log_dir / 'rl-deploy.log'),
             '--timeout', LaunchConfiguration('startup_timeout')],
        name='lite3_startup', output='screen', sigterm_timeout='8', sigkill_timeout='3')
    mission = Node(package='lite3_navigation', executable='mission_manager',
                   name='mission_manager', parameters=[os.path.join(navigation, 'config', 'mission.yaml'),
                     {'use_sim_time': True, 'enable_replanning': ParameterValue(
                       LaunchConfiguration('enable_replanning'), value_type=bool)}], output='screen')
    buffers = {}
    ready = False

    def observe(event, channel):
        nonlocal ready
        key = (event.pid, channel)
        text = buffers.get(key, '') + event.text.decode('utf-8', errors='replace')
        lines = text.split('\n')
        buffers[key] = lines.pop()[-4096:]
        actions = []
        for line in lines:
            # 确认来自实际插件的接管日志，不把发布请求当作接管成功。
            mode = None
            if '[Lite3 control] Mode: external' in line:
                mode = 'external'
            elif '[Lite3 control] Mode: stand' in line:
                mode = 'stand'
            if mode:
                temporary = mode_file.with_suffix('.tmp')
                temporary.write_text(json.dumps({'mode': mode, 'received': time.monotonic()}))
                temporary.replace(mode_file)
            if event.action is runtime and '[Lite3 startup] READY' in line and not ready:
                ready = True
                actions += [mission, LogInfo(msg='Lite3 已就绪：先开启 /lite3/set_navigation_enabled，再选点或输入终端目标。')]
        return actions

    def failed(event, context):
        if not context.is_shutdown:
            return [EmitEvent(event=Shutdown(reason=f'{event.process_name} 已退出，关闭本次完整启动。'))]
        return []

    map_server = Node(package='nav2_map_server', executable='map_server', name='map_server',
                      parameters=[{'yaml_filename': LaunchConfiguration('map_yaml'),
                                   'use_sim_time': True, 'bond_heartbeat_period': 0.0}], output='screen')
    planner = Node(package='nav2_planner', executable='planner_server', name='planner_server',
                   parameters=planner_parameters, output='screen')
    controller = Node(package='nav2_controller', executable='controller_server', name='controller_server',
                      parameters=[os.path.join(navigation, 'config', controller_config)],
                      additional_env={'OMP_NUM_THREADS': '1'},
                      remappings=[('cmd_vel', '/nav_cmd_vel')], output='screen')
    monitors = [RegisterEventHandler(OnProcessExit(target_action=node, on_exit=failed))
                for node in (runtime, map_server, planner, controller, mission)]
    return [
        RegisterEventHandler(OnProcessIO(on_stdout=lambda e: observe(e, 'out'),
                                         on_stderr=lambda e: observe(e, 'err'))),
        *monitors,
        LogInfo(msg=f'局部控制器：{profile}；任务受阻重规划按enable_replanning设置'),
        IncludeLaunchDescription(PythonLaunchDescriptionSource(os.path.join(gazebo, 'launch', 'simulation.launch.py')),
                                 launch_arguments={'gui': LaunchConfiguration('gui'),
                                                   'world': LaunchConfiguration('world'),
                                                   'paused': 'false',
                                                   'rviz': LaunchConfiguration('rviz'),
                                                   'fixed_frame': 'map',
                                                   'rviz_config': os.path.join(navigation, 'rviz', 'navigation.rviz')}.items()),
        Node(package='tf2_ros', executable='static_transform_publisher', name='map_to_odom',
             arguments=['--x', '0', '--y', '0', '--z', '0', '--roll', '0', '--pitch', '0', '--yaw', '0',
                        '--frame-id', 'map', '--child-frame-id', 'odom'], output='screen'),
        map_server, planner, controller, runtime,
    ]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('gui', default_value='true', description='显示 Gazebo 窗口'),
        DeclareLaunchArgument('rviz', default_value='true', description='显示导航 RViz'),
        DeclareLaunchArgument('controller', default_value='mppi', description='mppi持续局部避障；rpp原路线跟随回退'),
        DeclareLaunchArgument('planner', default_value='lattice', description='lattice完整轮廓/朝向；navfn旧中心线规划回退'),
        DeclareLaunchArgument('enable_replanning', default_value='true', description='受阻后等待和有限重规划'),
        DeclareLaunchArgument('world', default_value=os.path.join(
            get_package_share_directory('lite3_gazebo'), 'worlds', 'large_warehouse.sdf'),
            description='SDF绝对路径，world名须为large_warehouse'),
        DeclareLaunchArgument('map_yaml', default_value=os.path.join(
            get_package_share_directory('lite3_gazebo'), 'maps', 'large_warehouse.yaml'),
            description='与world对齐的静态地图yaml绝对路径'),
        DeclareLaunchArgument('rl_dir', default_value=str(Path.home() / 'Lite3_rl_deploy'),
                              description='已有官方 RL 部署项目根目录'),
        DeclareLaunchArgument('startup_timeout', default_value='120', description='自动准备总超时，实际秒'),
        OpaqueFunction(function=_start),
    ])
