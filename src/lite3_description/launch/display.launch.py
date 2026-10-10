import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


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

    with open(urdf_path, 'r') as file:
        robot_description = file.read()

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

        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            name='robot_state_publisher',
            parameters=[
                {
                    'robot_description': robot_description,
                    'use_sim_time': use_sim_time,
                }
            ],
            output='screen'
        ),

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
            arguments=[
                '-d',
                rviz_config_path,
                '-f',
                fixed_frame,
            ],
            parameters=[{'use_sim_time': use_sim_time}],
            output='screen'
        )

    ])
