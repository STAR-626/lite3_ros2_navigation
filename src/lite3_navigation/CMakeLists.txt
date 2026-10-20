cmake_minimum_required(VERSION 3.8)
project(lite3_navigation)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(gz_transport_vendor REQUIRED)
find_package(gz_msgs_vendor REQUIRED)
find_package(gz-transport13 REQUIRED)
find_package(gz-msgs10 REQUIRED)
find_package(Qt5 REQUIRED COMPONENTS Gui)
add_executable(place_marker_transport src/place_marker_transport.cpp)
target_compile_features(place_marker_transport PRIVATE cxx_std_17)
target_link_libraries(place_marker_transport PRIVATE gz-transport13::core gz-msgs10::gz-msgs10 Qt5::Gui)
install(TARGETS place_marker_transport DESTINATION lib/${PROJECT_NAME})
add_executable(environment_transport src/environment_transport.cpp)
target_compile_features(environment_transport PRIVATE cxx_std_17)
target_link_libraries(environment_transport PRIVATE gz-transport13::core gz-msgs10::gz-msgs10 Qt5::Core)
install(TARGETS environment_transport DESTINATION lib/${PROJECT_NAME})
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
  add_test(NAME agent_tools COMMAND /usr/bin/python3 -m unittest discover
    -s ${CMAKE_CURRENT_SOURCE_DIR}/test -p test_agent_tools.py -v)
  add_test(NAME approach_geometry COMMAND /usr/bin/python3 -m unittest discover
    -s ${CMAKE_CURRENT_SOURCE_DIR}/test -p test_approach_geometry.py -v)
  add_test(NAME environment_catalog COMMAND /usr/bin/python3 -m unittest discover
    -s ${CMAKE_CURRENT_SOURCE_DIR}/test -p test_environment_catalog.py -v)
  add_test(NAME language_context COMMAND /usr/bin/python3 -m unittest discover
    -s ${CMAKE_CURRENT_SOURCE_DIR}/test -p test_language_context.py -v)
  add_test(NAME deepseek_parser COMMAND /usr/bin/python3 -m unittest discover
    -s ${CMAKE_CURRENT_SOURCE_DIR}/test -p test_deepseek_parser.py -v)
  add_test(NAME language_worker COMMAND /usr/bin/python3 -m unittest discover
    -s ${CMAKE_CURRENT_SOURCE_DIR}/test -p test_language_worker.py -v)
  add_test(NAME interaction_core COMMAND /usr/bin/python3 -m unittest discover
    -s ${CMAKE_CURRENT_SOURCE_DIR}/test -p test_interaction_core.py -v)
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

install(PROGRAMS scripts/deepseek_setup.py DESTINATION lib/${PROJECT_NAME} RENAME deepseek_setup)
install(PROGRAMS scripts/deepseek_preview.py DESTINATION lib/${PROJECT_NAME} RENAME deepseek_preview)
install(PROGRAMS scripts/ai_console.py DESTINATION lib/${PROJECT_NAME} RENAME ai_console)
install(PROGRAMS scripts/interaction_backend.py DESTINATION lib/${PROJECT_NAME} RENAME interaction_backend)
install(FILES scripts/interaction_core.py scripts/place_markers.py scripts/deepseek_parser.py scripts/language_worker.py scripts/language_context.py scripts/environment_catalog.py scripts/environment_reader.py scripts/approach_geometry.py scripts/approach_executor.py scripts/agent_tools.py scripts/deepseek_agent.py scripts/agent_runtime.py DESTINATION lib/${PROJECT_NAME})

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
