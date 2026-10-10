# 当前成果恢复与启动手册

本手册按实际五个package、现有配置和外部RL恢复记录编写。首次安装见根README的
Ubuntu24.04/ROS2 Jazzy依赖清单；外部部署恢复见external/lite3_rl_deploy/README.md。
此处使用用户名ma；其他电脑需一致替换绝对路径。不要覆盖已有checkout或重复运行两套控制程序。

## 全新电脑恢复

仓库为PRIVATE，先获得访问权限并配置GitHub身份验证；目标目录不存在时：

```bash
git clone https://github.com/STAR-626/lite3_ros2_navigation.git /home/ma/lite3_ws
source /opt/ros/jazzy/setup.bash
cd /home/ma/lite3_ws
colcon build
source /home/ma/lite3_ws/install/setup.bash
```

外部RL锁定指定commit、初始化指定模型子模块、应用补丁、验证策略hash并构建，
按external说明完整执行。build/install/log和虚拟环境都是重建内容，不从GitHub恢复。
统一launch已设置Gazebo模型资源和插件路径，无需手工写入全局环境配置。
单独gz sim启动的资源变量说明保留在根README。

## 每次启动：目前仍是多终端联调

每个新ROS终端先source /opt/ros/jazzy/setup.bash和工作空间install/setup.bash。
以下持续运行命令各占一个终端；生命周期命令在另一个空闲已source终端执行。
不要把正在运行程序的终端当作shell输入新命令。

### 1．Gazebo、RViz、运动节点和桥接

```bash
ros2 launch lite3_gazebo simulation.launch.py
```

加载large_warehouse和Lite3，初始暂停，点击Gazebo播放。生成位置(-4,-4,0.365)。
统一launch已包含运动节点、桥接与模型TF，不再重复启动它们。

### 2．RL策略程序

```bash
cd /home/ma/Lite3_rl_deploy/build
./rl_deploy --ros-velocity
```

在此终端按z，等待至少4秒，再c；确认进入rl_control和ONNX ENTER。
另一个已source的终端请求接管：

```bash
gz topic -t /lite3/control_mode -m gz.msgs.StringMsg -p 'data: "external"'
```

不要同时运行MuJoCo；站着不等于RL已就绪。空格停止锁定后需要c解除RL层锁定。

### 3．地图发布

```bash
ros2 run nav2_map_server map_server --ros-args \
  -p yaml_filename:=/home/ma/lite3_ws/src/lite3_gazebo/maps/large_warehouse.yaml \
  -p use_sim_time:=true -p bond_heartbeat_period:=0.0
```

空闲终端：

```bash
ros2 lifecycle set /map_server configure
ros2 lifecycle set /map_server activate
```

### 4．临时map到odom变换

```bash
ros2 run tf2_ros static_transform_publisher \
  --x 0 --y 0 --z 0 --roll 0 --pitch 0 --yaw 0 \
  --frame-id map --child-frame-id odom
```

当前真值odom与world对齐，map→odom为零变换。地图图片origin不是需要额外叠加的TF。
RViz选择Fixed Frame=map，添加/map和/plan以观察；地图订阅使用Transient Local/Reliable。

### 5．全局规划器

```bash
ros2 run nav2_planner planner_server --ros-args \
  --params-file /home/ma/lite3_ws/install/lite3_navigation/share/lite3_navigation/config/planner.yaml
```

空闲终端：

```bash
ros2 lifecycle set /planner_server configure
ros2 lifecycle set /planner_server activate
```

### 6．路线跟随控制器

```bash
ros2 run nav2_controller controller_server --ros-args \
  --params-file /home/ma/lite3_ws/install/lite3_navigation/share/lite3_navigation/config/controller.yaml \
  -r cmd_vel:=/nav_cmd_vel
```

空闲终端：

```bash
ros2 lifecycle set /controller_server configure
ros2 lifecycle set /controller_server activate
```

使用Twist，导航只发布/nav_cmd_vel。期望前进0.32m/s、原地转向0.6rad/s、最大角加速度12rad/s²。
这些是当前实测配置，不是任意地形的性能承诺。

### 7．任务节点

```bash
ros2 run lite3_navigation mission_manager --ros-args -p use_sim_time:=true
```

这里只等待，不自动移动。不能与mission_manager_once并行控制机器人。

### 8．用户任务与取消

先确认旧任务已结束，RL和external已就绪，读取实际位置，显式解锁后发可通行目标：

```bash
ros2 topic echo /odom --once
ros2 service call /lite3/set_stop std_srvs/srv/SetBool '{data: false}'
ros2 action send_goal /navigate_task lite3_interfaces/action/NavigateTask \
  '{goal_x: 4.0, goal_y: 4.0, goal_yaw: 0.0}' --feedback
```

如已在(4,4)附近，换一个可通行目标，避免立即成功被误认为新行走验证。
取消在另一个终端：

```bash
ros2 service call /navigate_task/_action/cancel_goal action_msgs/srv/CancelGoal '{}'
```

取消/失败/超时保持停止锁定；最终结果确认清理完成后才能决定解锁发新任务。
紧急锁输入用/lite3/set_stop(true)，但它本身不取消任务。Ctrl+C不代替取消。
停止开发前先取消并确认，再退出其他程序；RL退出前请求stand，固定站立不保证倒地恢复。

## 验证范围

旧单次入口真实短直线和仓库长路线通过，新常驻入口16项隔离协议检查通过，
本手册没有在全新电脑完整安装或重新启动用户GUI验证。下一步仍是用户实际Gazebo新入口验收。
地图/生命周期管理合并尚未实现，因此多终端只是当前阶段，不更改原9节点总体设计。
