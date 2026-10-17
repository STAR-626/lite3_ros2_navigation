cmake_minimum_required(VERSION 3.8)
project(lite3_gazebo)

if(POLICY CMP0100)
  cmake_policy(SET CMP0100 NEW)
endif()

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(gz_gui_vendor REQUIRED)
find_package(gz_plugin_vendor REQUIRED)
find_package(gz_transport_vendor REQUIRED)
find_package(gz_msgs_vendor REQUIRED)
find_package(gz_sim_vendor REQUIRED)
find_package(gz-gui8 REQUIRED)
find_package(gz-plugin2 REQUIRED COMPONENTS register)
find_package(gz-transport13 REQUIRED)
find_package(gz-msgs10 REQUIRED)
find_package(gz-sim8 REQUIRED)
find_package(Qt5 REQUIRED COMPONENTS Core Quick QuickControls2)

set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTORCC ON)
add_library(Lite3TargetPicker SHARED
  gui/Lite3TargetPicker.hh gui/Lite3TargetPicker.cc gui/target_picker.qrc)
target_compile_features(Lite3TargetPicker PRIVATE cxx_std_17)
target_link_libraries(Lite3TargetPicker PRIVATE
  gz-gui8::gz-gui8 gz-plugin2::gz-plugin2-register
  gz-transport13::core gz-msgs10::gz-msgs10
  Qt5::Core Qt5::Quick Qt5::QuickControls2)
install(TARGETS Lite3TargetPicker LIBRARY DESTINATION lib)
add_library(Lite3BoxContacts SHARED src/BoxContacts.cc)
target_compile_features(Lite3BoxContacts PRIVATE cxx_std_17)
target_link_libraries(Lite3BoxContacts PRIVATE
  gz-sim8::gz-sim8 gz-plugin2::gz-plugin2-register
  gz-transport13::core gz-msgs10::gz-msgs10)
install(TARGETS Lite3BoxContacts LIBRARY DESTINATION lib)
install(FILES gui/LICENSE DESTINATION share/${PROJECT_NAME}
  RENAME LICENSE.target-picker.BSD-3-Clause.txt)
install(FILES gui/LICENSE DESTINATION share/${PROJECT_NAME}
  RENAME LICENSE.box-contacts.BSD-3-Clause.txt)
# uncomment the following section in order to fill in
# further dependencies manually.
# find_package(<dependency> REQUIRED)

if(BUILD_TESTING)
  add_executable(check_target_picker test/check_target_picker.cc)
  target_include_directories(check_target_picker PRIVATE gui)
  add_dependencies(check_target_picker Lite3TargetPicker)
  target_link_libraries(check_target_picker PRIVATE
    gz-gui8::gz-gui8 gz-transport13::core gz-msgs10::gz-msgs10
    Qt5::Core Qt5::Quick)
  target_compile_features(check_target_picker PRIVATE cxx_std_17)
  add_test(NAME target_picker_interaction COMMAND check_target_picker)
  set_tests_properties(target_picker_interaction PROPERTIES TIMEOUT 30
    ENVIRONMENT "QT_QPA_PLATFORM=offscreen;QT_QUICK_BACKEND=software;GZ_GUI_PLUGIN_PATH=$<TARGET_FILE_DIR:Lite3TargetPicker>")
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
  DIRECTORY worlds launch maps config
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
