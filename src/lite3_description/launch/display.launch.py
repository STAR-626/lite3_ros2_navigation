import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def _start_state_publisher(context):
    # 仿真传入它实际生成的 URDF，保证传感器位置和 Gazebo 一致。
    with open(LaunchConfiguration('urdf_file').perform(context), 'r') as file:
        robot_description = file.read()
    return [Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        parameters=[{
            'robot_description': robot_description,
            'use_sim_time': ParameterValue(
                LaunchConfiguration('use_sim_time'), value_type=bool),
        }],
        output='screen',
    )]


def generate_launch_description():
    package_path = get_package_share_directory('lite3_description')

    urdf_path = os.path.join(
        package_path,
        'urdf',
        'Lite3.urdf'
    )

    rviz_config_path = os.path.join(
        package_path,
        'rviz',
        'lite3.rviz'
    )

    use_gui = LaunchConfiguration('use_gui')
    fixed_frame = LaunchConfiguration('fixed_frame')
    use_sim_time = ParameterValue(
        LaunchConfiguration('use_sim_time'),
        value_type=bool
    )

    return LaunchDescription([
        # 单独展示模型时保留滑块，使用电脑时间。
        DeclareLaunchArgument('use_gui', default_value='true'),
        DeclareLaunchArgument('use_sim_time', default_value='false'),
        DeclareLaunchArgument('fixed_frame', default_value='TORSO'),
        DeclareLaunchArgument('rviz', default_value='true'),
        DeclareLaunchArgument('rviz_config', default_value=rviz_config_path),
        DeclareLaunchArgument('urdf_file', default_value=urdf_path),

        OpaqueFunction(function=_start_state_publisher),

        Node(
            package='joint_state_publisher_gui',
            executable='joint_state_publisher_gui',
            name='joint_state_publisher_gui',
            condition=IfCondition(use_gui),
            parameters=[{'use_sim_time': use_sim_time}],
            output='screen'
        ),

        Node(
            package='rviz2',
            executable='rviz2',
            name='rviz2',
            condition=IfCondition(LaunchConfiguration('rviz')),
            arguments=[
                '-d',
                LaunchConfiguration('rviz_config'),
                '-f',
                fixed_frame,
            ],
            parameters=[{'use_sim_time': use_sim_time}],
            output='screen'
        )

    ])
