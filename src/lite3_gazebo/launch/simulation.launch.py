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
        gazebo_package_path, 'worlds', 'lite3_empty.sdf'
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
            '-world', 'lite3_world',
            '-file', urdf_path,
            '-name', 'Lite3',
            '-x', '0.0',
            '-y', '0.0',
            # 初始站姿的脚底接近地面，避免高处落地冲击压弯后腿。
            '-z', '0.36',
        ],
        output='screen'
    )

    # 复用我们已经写好的模型显示启动文件。
    start_display = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(display_launch_path)
    )

    return LaunchDescription([
        set_resource_path,
        set_plugin_path,
        start_gazebo,
        spawn_lite3,
        start_display,
    ])
