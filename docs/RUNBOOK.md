# 当前成果恢复与启动手册

**2026-10-17 完整轮廓与受阻优化（当前版本）：** 默认全局规划改为Smac Lattice，
在5cm地图上结合机身朝向和0.84×0.40m矩形检查路线；MPPI允许必要的短距离后退（最低-0.30m/s）。
受阻恢复增加近期失败路段软代价，促使有替代路线时换路；不把失败路段当作真实障碍。
RViz只默认显示当前接受执行的路线，结束/恢复清空，并显示任务状态；状态查询保留最后结果。
总开关、任务Action、20cm内切半径、RL和原整体规划保持；未新增常驻节点。
操作、回退、错误及新增话题见[终端手册](TERMINAL_COMMANDS.md)顶部，
本轮证据和限制见[完整轮廓优化记录](FOOTPRINT_REPLANNING.md)。较早NavFn说明为历史阶段。


**2026-10-17 持续避让：** 默认MPPI替换局部RPP（原配置仍可回退）；
雷达短期运动估计→独立预测costmap层→局部绕行，受阻后等待/有限重规划。
日常启动与导航输入不变；新增依赖、四包构建、移动箱子工具和参数见
[终端手册](TERMINAL_COMMANDS.md)，实测边界见[持续避让说明](CONTINUOUS_AVOIDANCE.md)。
仍是平地/已知地图方案，SLAM和复杂地形未实现。下方较早检查点为历史记录。

**2026-10-14 三维雷达：** 完整bringup命令不变，新增lite3_perception处理节点。
升级后/scan是二维障碍投影，原始三维点云为/lite3/lidar/points。
全局/局部costmap接入障碍/清除点云；平地高度/自身筛选、可视化和新接口见
[终端手册第9.1节](TERMINAL_COMMANDS.md#91-三维雷达平地过滤与二维障碍地图2026-10-14)。
本次新增运行依赖由lite3_perception/package.xml声明；新电脑可用rosdep安装后构建。
SLAM、起伏地面识别、自动重规划仍是后续。下方二维雷达记录为上一阶段。

日常终端命令集中维护于[终端交互操作手册](TERMINAL_COMMANDS.md)；
本文侧重新电脑恢复和完整启动/调试说明。最新操作及单位/停止规则优先查操作手册。

**雷达更新（2026-10-13）：** 二维模拟雷达、/scan桥接、lidar_link TF和导航RViz
扫描显示已构建安装。完整启动命令不变；独立扫描、频率/TF检查及构建命令见
[终端手册第9.1节](TERMINAL_COMMANDS.md#91-雷达扫描验收2026-10-13)。
目前尚未将扫描送入Nav2障碍层或SLAM；不能把扫描显示称为已完成动态避障。

**最新交互（2026-10-13）：** 任务节点现在默认关闭导航总开关。启动后先执行
`ros2 service call /lite3/set_navigation_enabled std_srvs/srv/SetBool '{data: true}'`，
成功后可用Gazebo新选点立即导航，或 `ros2 run lite3_navigation navigate X Y 角度`。
应用本次代码、关闭/取消、非法目标与度数/弧度说明见 [交互手册](NAVIGATION_INTERACTION.md)。
下面2026-10-12“只选点”段落为历史阶段，新版行为以上述手册为准。

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

## Gazebo 选点预览（2026-10-12）

本阶段只选目标位置，不发任务。已编译的新插件需要重启 Gazebo 才能加载；
若有正在执行的导航任务，先按已有取消步骤确认任务结束，再退出原 launch。
重新 source Jazzy 和工作空间，运行原 `ros2 launch lite3_navigation bringup.launch.py` 即可。

1. 找到 Gazebo 内“Lite3 目标选点”面板，点击“选择目标”。
2. 单击空闲地面，出现橙色标记和 X/Y/地面高度；拖动视角不会选点。
3. 点击“复制坐标”可粘贴到终端目标参数中；复制本身不会启动导航。
4. 重新选择需再次点“选择目标”；“取消选点”保留上次选中位置。

另一个已 source 的终端可检查：

```bash
ros2 topic echo /lite3/selected_goal --once
```

消息类型为 `geometry_msgs/msg/PoseStamped`，frame_id 为 `map`；x/y 为米，
z 为点击表面高度，默认姿态四元数 w=1。点击事件来自 Gazebo GUI，插件发布
Gazebo Transport `gz.msgs.Pose`，已有 `ros_gz_bridge` 单向转换，未增加 ROS 节点。
当前 world/map/odom 原点和轴一致；未来若改变 map→odom 或定位方案，需要坐标转换。
选择后按2Hz重复发布当前坐标，便于晚打开的终端读取；没有用户确认就不会发 Action。

橙色标记只存在于 GUI，没有碰撞体，不改变场景或地图。当前以高度范围
[-0.02,0.15]m 筛选近地面点击，高货架/天空和非有限坐标会拒绝；这不是可通行性
检查，低矮障碍和地图占据状态要在后续任务提交时检查。此阶段不选择朝向，
不跨重启保存选点，也没有“开始导航”按钮。下一步复用现有 `/navigate_task` 接入。

GUI 采用项目提供的默认布局，未覆盖用户的 Gazebo 全局配置。
单模块调试 `simulation.launch.py target_picker:=false` 可以关闭新布局。
构建新组件需要 Qt5 和 `gz_gui_vendor`，本机已具备，安装命令见根 README。

开发者复测（先 source ROS/工作空间、构建 lite3_gazebo）：

```bash
ctest --test-dir /home/ma/lite3_ws/build/lite3_gazebo -R '^target_picker_interaction$' --output-on-failure
python3 /home/ma/lite3_ws/src/lite3_gazebo/test/check_picker_bridge.py
```

测试加载真实插件和 QML、注入标准场景事件，检查拖动/高度/NaN过滤、复制、
目标话题、GUI标记请求及退出清理；桥接检查用独立ROS域182和Gazebo分区。
不启动RL或发送导航/速度。这不代替真实三维窗口中的鼠标点击与标记可见性验收。

## 完整系统简化启动（2026-10-12）

已新增 `ros2 launch lite3_navigation bringup.launch.py`。日常只需要两个终端：一个保持整套系统运行，另一个发送任务或检查状态。
它自动加载仓库、生成 Lite3、播放仿真、打开导航 RViz、启动运动/桥接/模型节点、加载安装目录中的地图、发布 map→odom、配置并激活 Nav2、准备已有 RL 程序，确认 Gazebo external 接管后再启动常驻 mission_manager。
不会自动发送导航目标。原来的单模块和多终端方式仍可调试，但不要与完整入口同时运行。

修改后首次构建（本机此次已完成）：

```bash
source /opt/ros/jazzy/setup.bash
cd /home/ma/lite3_ws
colcon build --packages-select lite3_description lite3_gazebo lite3_navigation
```

终端 1，每次启动：

```bash
source /opt/ros/jazzy/setup.bash
source /home/ma/lite3_ws/install/setup.bash
ros2 launch lite3_navigation bringup.launch.py
```

等待 `[Lite3 startup] READY` 和任务节点的启动提示。无需手动点击播放、按 z/c、发布 external 或逐个调用 lifecycle。
RL 源码与策略未改变，仍使用 `/home/ma/Lite3_rl_deploy/build/rl_deploy --ros-velocity`；启动辅助程序用伪终端完成原有 z/c 准备，依据仿真数据、生命周期响应、策略进入日志和实际插件接管日志确认顺序，不是固定 sleep 后假定就绪。
临时 ROS 节点 `lite3_startup` 就绪后销毁，辅助进程继续监管其自己启动的 RL。启动阶段先锁定速度，完成后解除本次启动锁定；运行阶段仍沿用原任务失败/取消后显式解锁的规则。

终端 2：

```bash
source /opt/ros/jazzy/setup.bash
source /home/ma/lite3_ws/install/setup.bash
ros2 action send_goal /navigate_task lite3_interfaces/action/NavigateTask \
  '{goal_x: 4.0, goal_y: 4.0, goal_yaw: 0.0}' --feedback
```

取消、返回基地和模式切换仍使用已有接口，详见 TERMINAL_COMMANDS。取消/失败后先确认清理完成，再按需显式解除停止锁定，不由 launch 自动恢复旧任务。
退出时先取消并确认正在执行的任务结束，再在终端 1 按 Ctrl+C；launch 回收本次启动的组件和 RL。等待退出完成后再启动，Gazebo 包装进程退出时端口可能短暂延后释放。

可选参数：`gui:=false rviz:=false` 不打开窗口，`rl_dir:=/实际路径/Lite3_rl_deploy` 指定已有外部项目，`startup_timeout:=180` 延长启动总等待（实际秒）。
端口 20001/30010/30011 被占用，或同一 ROS 域已有本项目节点时拒绝重复启动，不自动杀其他进程。初始暂停或反复重启导致启动失败时查看启动终端日志。
完整 RL 原始输出写入本次 ROS launch 日志目录的 `rl-deploy.log`。终端显示重要状态，不需要用户打开额外 RL 终端。
模型、地图、RL 权重、控制器速度、任务协议和未来规划均保持原样。

## 单独调试：原多终端联调步骤

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
  --params-file /home/ma/lite3_ws/install/lite3_navigation/share/lite3_navigation/config/planner_navfn.yaml
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
上述为原多终端检查点。2026-10-12 完整 launch 已接入启动阶段地图和生命周期管理，原总体设计不变。

### 本次实际验证（2026-10-12）

三包构建及新旧 launch 参数查询通过。在 ROS_DOMAIN_ID=180、独立 Gazebo 分区中实际启动无 GUI 完整系统：地图、规划器、控制器均 active（3）；地图224×224；12关节、map→TORSO TF、/navigate_task 服务端正常；就绪后临时 startup ROS 节点已销毁；运动/任务节点各一个，导航速度发布者一个。RL 自动 idle→standup→rl_control、ONNX ENTER，实际插件确认 external；默认零速下机器人稳定在约(-3.994,-4.000)。没有发送导航目标或非零速度，此验证不替代用户 GUI/新路线行走验收。
已发 SIGINT 结束此次 launch，自己的 RL 和节点退出，20001/30010/30011 全部释放；Gazebo 的 Ruby 包装进程由 launch 的 SIGTERM 超时回收机制结束。另验证 RL 文件缺失、UDP30011占用、同一ROS域遗留map_server均在启动组件之前拒绝，且不终止其他进程；空ROS域接受完整启动计划。
初次测试发现本机rclpy未提供qos_profile_clock，已改为明确的best-effort时钟QoS并构建、重新通过上述实际启动。无额外系统安装、无RL源码修改、无Git提交/推送。
