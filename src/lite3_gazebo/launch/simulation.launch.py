import os
import shlex

from ament_index_python.packages import (
    get_package_share_directory,
    get_package_prefix,
)
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, SetEnvironmentVariable
from launch.launch_description_sources import PythonLaunchDescriptionSource

from launch_ros.actions import Node


def generate_launch_description():
    # 找到三个包的安装资源目录。
    gazebo_package_path = get_package_share_directory('lite3_gazebo')
    description_package_path = get_package_share_directory('lite3_description')
    ros_gz_package_path = get_package_share_directory('ros_gz_sim')

    # 找到世界、机器人模型和启动文件。
    world_path = os.path.join(
        gazebo_package_path, 'worlds', 'large_warehouse.sdf'
    )

    urdf_path = os.path.join(
        description_package_path, 'urdf', 'Lite3_gazebo.urdf'
    )

    gazebo_launch_path = os.path.join(
        ros_gz_package_path, 'launch', 'gz_sim.launch.py'
    )

    display_launch_path = os.path.join(
        description_package_path, 'launch', 'display.launch.py'
    )

    # Gazebo 需要从模型包的父目录查找 package:// 模型资源。
    resource_paths = [os.path.dirname(description_package_path)]

    existing_resource_path = os.environ.get('GZ_SIM_RESOURCE_PATH', '')
    if existing_resource_path:
        resource_paths.append(existing_resource_path)

    set_resource_path = SetEnvironmentVariable(
        name='GZ_SIM_RESOURCE_PATH',
        value=os.pathsep.join(resource_paths)
    )

    plugin_paths = [
        os.path.join(get_package_prefix('lite3_control'), 'lib')
    ]

    existing_plugin_path = os.environ.get(
        'GZ_SIM_SYSTEM_PLUGIN_PATH', ''
    )
    if existing_plugin_path:
        plugin_paths.append(existing_plugin_path)

    set_plugin_path = SetEnvironmentVariable(
        name='GZ_SIM_SYSTEM_PLUGIN_PATH',
        value=os.pathsep.join(plugin_paths)
    )

    # 复用官方 Gazebo 启动文件；不加 -r，初始保持暂停。
    start_gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(gazebo_launch_path),
        launch_arguments={
            'gz_args': f'-v 3 {shlex.quote(world_path)}',
            'on_exit_shutdown': 'true',
        }.items()
    )

    # 请求在世界中生成机器人。
    spawn_lite3 = Node(
        package='ros_gz_sim',
        executable='create',
        name='spawn_lite3',
        arguments=[
            '-world', 'large_warehouse',
            '-file', urdf_path,
            '-name', 'Lite3',
            '-x', '-4.0',
            '-y', '-4.0',
            # 初始站姿的脚底接近地面，避免高处落地冲击压弯后腿。
            '-z', '0.365',
        ],
        output='screen'
    )

    # 仿真时关闭滑块，使用 Gazebo 的关节状态和仿真时间。
    start_display = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(display_launch_path),
        launch_arguments={
            'use_gui': 'false',
            'use_sim_time': 'true',
            'fixed_frame': 'odom',
        }.items()
    )

    # 单向桥接实际关节、机身状态和时钟，统一 ROS2 侧的话题名称。
    start_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='ros_gz_bridge',
        arguments=[
            '/lite3/joint_states@sensor_msgs/msg/JointState[gz.msgs.Model',
            '/world/large_warehouse/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock',
            '/lite3/ground_truth/odom@nav_msgs/msg/Odometry[gz.msgs.Odometry',
        ],
        remappings=[
            ('/lite3/joint_states', '/joint_states'),
            ('/world/large_warehouse/clock', '/clock'),
        ],
        output='screen'
    )

    # 启动运动节点，接收 ROS2 速度并转发给 RL 程序。
    start_motion = Node(
        package='lite3_control',
        executable='lite3_motion_node',
        name='lite3_motion_node',
        parameters=[{'use_sim_time': True}],
        output='screen'
    )

    return LaunchDescription([
        set_resource_path,
        set_plugin_path,
        start_gazebo,
        spawn_lite3,
        start_bridge,
        start_display,
        start_motion,
    ])
