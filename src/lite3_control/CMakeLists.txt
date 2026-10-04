cmake_minimum_required(VERSION 3.8)
project(lite3_control)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(gz_sim_vendor REQUIRED)
find_package(gz_plugin_vendor REQUIRED)
find_package(gz_transport_vendor REQUIRED)
find_package(gz_msgs_vendor REQUIRED)

find_package(gz-sim8 REQUIRED)
find_package(gz-plugin2 REQUIRED COMPONENTS register)
find_package(gz-transport13 REQUIRED)
find_package(gz-msgs10 REQUIRED)
# uncomment the following section in order to fill in
# further dependencies manually.
# find_package(<dependency> REQUIRED)

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

add_library(lite3_gazebo_interface SHARED
  src/lite3_gazebo_interface.cpp
)

target_compile_features(lite3_gazebo_interface PRIVATE cxx_std_17)

target_link_libraries(lite3_gazebo_interface PRIVATE
  gz-sim8::gz-sim8
  gz-plugin2::gz-plugin2-register
  gz-transport13::core
  gz-msgs10::gz-msgs10
)

install(
  TARGETS lite3_gazebo_interface
  LIBRARY DESTINATION lib
)

ament_package()
