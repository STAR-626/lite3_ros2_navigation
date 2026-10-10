cmake_minimum_required(VERSION 3.8)
project(lite3_interfaces)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(action_msgs REQUIRED)

# 从任务格式生成 C++/Python 等接口，不创建可执行节点。
rosidl_generate_interfaces(${PROJECT_NAME}
  "action/NavigateTask.action"
  DEPENDENCIES geometry_msgs
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
