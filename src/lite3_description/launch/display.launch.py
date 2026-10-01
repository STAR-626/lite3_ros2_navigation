import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


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

    return LaunchDescription([

        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            name='robot_state_publisher',
            parameters=[
                {'robot_description': robot_description}
            ],
            output='screen'
        ),

        Node(
            package='joint_state_publisher_gui',
            executable='joint_state_publisher_gui',
            name='joint_state_publisher_gui',
            output='screen'
        ),

        Node(
            package='rviz2',
            executable='rviz2',
            name='rviz2',
            arguments=[
                '-d',
                rviz_config_path
            ],
            output='screen'
        )

    ])
