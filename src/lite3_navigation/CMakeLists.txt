cmake_minimum_required(VERSION 3.8)
project(lite3_navigation)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(nav2_planner REQUIRED)
find_package(nav2_navfn_planner REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_action REQUIRED)
find_package(nav2_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(lite3_interfaces REQUIRED)
find_package(std_srvs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(visualization_msgs REQUIRED)
find_package(tf2_ros REQUIRED)
find_package(tf2_geometry_msgs REQUIRED)
find_package(nav2_core REQUIRED)
find_package(pluginlib REQUIRED)
find_package(nav2_mppi_controller REQUIRED)

add_library(lite3_response_critic SHARED src/rl_response_critic.cpp)
target_compile_features(lite3_response_critic PRIVATE cxx_std_17)
ament_target_dependencies(lite3_response_critic nav2_mppi_controller pluginlib)
pluginlib_export_plugin_description_file(nav2_mppi_controller critic_plugins.xml)
install(TARGETS lite3_response_critic LIBRARY DESTINATION lib)

add_library(lite3_avoidance_controller SHARED src/avoidance_controller.cpp)
target_compile_features(lite3_avoidance_controller PRIVATE cxx_std_17)
ament_target_dependencies(lite3_avoidance_controller nav2_core pluginlib tf2_ros tf2_geometry_msgs rclcpp)
pluginlib_export_plugin_description_file(nav2_core controller_plugins.xml)
install(TARGETS lite3_avoidance_controller LIBRARY DESTINATION lib)
install(FILES LICENSE DESTINATION share/${PROJECT_NAME})

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  # the following line skips the linter which checks for copyrights
  # comment the line when a copyright and license is added to all source files
  set(ament_cmake_copyright_FOUND TRUE)
  # the following line skips cpplint (only works in a git repo)
  # comment the line when this package is in a git repo and when
  # a copyright and license is added to all source files
  set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()
endif()

install(
  DIRECTORY config launch rviz
  DESTINATION share/${PROJECT_NAME}
)

install(PROGRAMS scripts/bringup_runtime.py DESTINATION lib/${PROJECT_NAME})
install(PROGRAMS scripts/navigate.py DESTINATION lib/${PROJECT_NAME} RENAME navigate)
install(PROGRAMS scripts/moving_obstacle.py DESTINATION lib/${PROJECT_NAME} RENAME moving_obstacle)

add_executable(mission_manager src/mission_manager.cpp)

target_compile_features(mission_manager PRIVATE cxx_std_17)

ament_target_dependencies(mission_manager
  rclcpp
  rclcpp_action
  nav2_msgs
  geometry_msgs
  lite3_interfaces
  std_srvs
  std_msgs
  visualization_msgs
  tf2_ros
)

# 保留已验证的单次启动参数入口，和常驻任务节点择一运行。
add_executable(mission_manager_once src/mission_manager_once.cpp)
target_compile_features(mission_manager_once PRIVATE cxx_std_17)
ament_target_dependencies(mission_manager_once rclcpp rclcpp_action nav2_msgs geometry_msgs)

install(
  TARGETS mission_manager mission_manager_once
  DESTINATION lib/${PROJECT_NAME}
)

ament_package()
