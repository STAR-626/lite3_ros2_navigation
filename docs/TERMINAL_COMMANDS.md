# Lite3 项目终端交互操作手册

**最后更新：2026-10-17。** 本文是日常终端命令的统一入口，按实际项目源码维护。
以后新增或修改命令、接口、参数、错误信息和操作顺序时，同步更新本文。

项目：`/home/ma/lite3_ws`；外部 RL：`/home/ma/Lite3_rl_deploy`。
命令中的路径适用于本机。导航目标位置属于 map，单位是米。

> 最新“只读状态查询”已写入源码、隔离构建并测试。若当前运行的节点还没有
> `/lite3/get_navigation_state`，先执行第2节的更新流程。
> source 只让终端找到安装内容，不会让已经运行的旧节点自动升级。


## 本轮优化：完整轮廓规划、受阻换路和任务显示（2026-10-17）

本轮已安装 Smac；源码/安装状态和实际测试见 SESSION_HANDOFF 顶部。
整体节点分工、RL策略、雷达、导航总开关和20cm内切半径保持原方案。
默认全局规划改为 Smac Lattice，矩形实际外沿仍0.84×0.40m，地图分辨率须匹配5cm运动集。
规划检查朝向与转弯，允许必要的后退；途中MPPI速度范围改为[-0.30,0.40]m/s，仍优先前进。
这是离散地图检查，不保证完整步态外摆或任意运动障碍下的物理安全。

**终端1：** 旧系统退出后构建；不在运行Gazebo时覆盖插件。

```bash
source /opt/ros/jazzy/setup.bash
source /home/ma/lite3_ws/install/setup.bash
cd /home/ma/lite3_ws
# 新电脑需要安装；本机用户已经完成
sudo apt-get install ros-jazzy-nav2-smac-planner
colcon build --packages-select lite3_perception lite3_navigation
source /home/ma/lite3_ws/install/setup.bash
ros2 launch lite3_navigation bringup.launch.py
```

没有改源码时直接正常启动即可。启动仍不自动行走，总开关默认关闭。
用于对比旧全局算法时，将最后一条命令换成下面这条，不能两套同时启动：

```bash
ros2 launch lite3_navigation bringup.launch.py planner:=navfn
```

此回退不具备Lattice的朝向轮廓检查或失败路段偏好层，执行阶段碰撞检查保留。
`controller:=rpp`依旧可用，launch同时关闭Lattice后退扩展，保持动作一致；默认Lattice+MPPI为本轮测试组合。
launch自动从已安装nav2_smac_planner的share目录找到diff/output.json，不复制第三方整包。
单独运行planner_server时必须额外传GridBased.lattice_filepath的实际完整路径，不能直接使用空占位。

**终端2：** 准备环境后，先只读查询，再显式开启，再给目标；位置单位米、角度单位度。

```bash
source /opt/ros/jazzy/setup.bash
source /home/ma/lite3_ws/install/setup.bash
ros2 service call /lite3/get_navigation_state std_srvs/srv/Trigger '{}'
ros2 service call /lite3/set_navigation_enabled std_srvs/srv/SetBool '{data: true}'
ros2 run lite3_navigation navigate 4.0 3.5 0
```

上面目标用于当前原仓库测试，不能保证你额外放入箱子之后仍可达。
原(4,4,0°)在一次实时雷达图中机器人轮廓压到障碍边缘；不能仅看目标中心在空地就判断有效。
新规划器目标容差为0：必须能在指定位置/朝向放下轮廓；执行到达容差仍约20cm/0.20rad，未改。
目标轮廓被挡返回任务结果3（INVALID_GOAL），当前轮廓受阻返回2（BLOCKED）；无可行路径返回1。
Nav2原始错误206是目标占用，205是起点占用，207是规划超时，208是无路；不要与任务结果编号混淆。
失败后仍关闭总开关并锁定停止，检查原因、重新开启后再试。

RViz默认显示`Active Navigation Route`，只在控制器接受执行路线后显示，恢复/结束时清空。
机器狗上方`Navigation Task Status`显示FOLLOWING、REPLANNING、ARRIVED或BLOCKED。
原`/plan`仅是规划输出，可能残留；默认关闭的`Planner Preview (debug; not an active task)`可临时勾选做规划预览。
只做规划预览时没有执行路线是正常的。

状态查询新增`last_result_code`和`last_result_message`；启动时分别null和空字符串。
任务结束即使phase回到IDLE，也可查看上次为何结束；查询不会解除停止或自动发任务。
以下都是只读诊断，持续echo用Ctrl+C退出：

```bash
ros2 topic echo /lite3/navigation_marker --once --qos-durability transient_local
ros2 topic echo /lite3/navigation_path --once --qos-durability transient_local
ros2 param get /planner_server GridBased.plugin
ros2 param get /planner_server GridBased.allow_reverse_expansion
ros2 param get /controller_server FollowPath.vx_min
```

新增显示话题均可靠、transient_local、depth1：

|话题|类型|发布者 → 订阅者|内容|
|---|---|---|---|
|/lite3/navigation_path|nav_msgs/msg/Path|mission_manager → RViz|当前接受执行的路线；空Path清除|
|/lite3/navigation_marker|visualization_msgs/msg/Marker|mission_manager → RViz|持续可见的任务状态文字|
|/lite3/avoidance/failed_route|nav_msgs/msg/Path|mission_manager → global_costmap内RoutePenaltyLayer|近期走不通路段的偏好提示，不是真实传感器障碍|

失败路段在机器人前方约0.5～1.3米、避开目标最后0.5米，最多180点。
全局层半径0.18米、原始代价200（低于碰撞阈值253），12实际秒过期，结束时主动清除。
它促使存在替代路时换路，不能制造新通道，也不能保证每次路线都不同。
终点RPP若预测碰撞，则交还保留碰撞检查的MPPI机动，2实际秒后再尝试RPP；
参数为FollowPath.goal_approach_retry，默认2.0，不直接放大或伪造速度。
恢复仍先暂停、确认取消、0.5秒起等待、最多5次；无进展判定3秒，旋转也计入进展。
新增层/显示均复用现有节点，没有新增常驻ROS节点。退出仍在终端1按Ctrl+C。

## 目录

1. [每个新终端先准备环境](#1-每个新终端先准备环境)
2. [修改代码后构建更新](#2-修改代码后构建更新)
3. [启动完整系统](#3-启动完整系统)
4. [查询总开关和任务状态](#4-查询总开关和任务状态)
5. [开启导航总开关](#5-开启导航总开关)
6. [发送目标与返回出发点](#6-发送目标与返回出发点)
7. [停止、取消与重新开启](#7-停止取消与重新开启)
8. [手动速度和键盘控制](#8-手动速度和键盘控制)
9. [查看位置、消息和通信接口](#9-查看位置消息和通信接口)
10. [查看速度参数和错误含义](#10-查看速度参数和错误含义)
11. [正常退出](#11-正常退出)
12. [单模块调试入口](#12-单模块调试入口)
13. [常用操作速查表](#13-常用操作速查表)
14. [维护与更新记录](#14-维护与更新记录)

## 1. 每个新终端先准备环境

```bash
source /opt/ros/jazzy/setup.bash
source /home/ma/lite3_ws/install/setup.bash
```

第一条加载 ROS2 Jazzy；第二条让本终端找到我们编译安装的包、节点和接口。
每个新终端都要执行；不会启动机器人。

日常一般两个终端就够：

- **终端1：** 保持整套系统运行，查看后台日志。
- **终端2：** 查询、开启/关闭导航、发送目标或手动控制。
- `navigate`、键盘控制和持续 `topic echo/pub` 会占用终端；需要同时操作时可临时再开一个终端。

## 2. 修改代码后构建更新

**先结束任务并退出旧启动，再构建。** 不在 Gazebo 运行时覆盖其已经加载的插件库。

只更新导航包（例如补充状态查询）：

```bash
source /opt/ros/jazzy/setup.bash
source /home/ma/lite3_ws/install/setup.bash
cd /home/ma/lite3_ws
colcon build --packages-select lite3_navigation
source /home/ma/lite3_ws/install/setup.bash
```

同时修改选点插件或 Gazebo 启动配置时，把构建命令改为：

```bash
colcon build --packages-select lite3_gazebo lite3_navigation
```

修改雷达模型、桥接或RViz配置时，构建这三个包（本次2026-10-14已构建）：

```bash
colcon build --packages-select lite3_perception lite3_description lite3_gazebo lite3_navigation
```

需要构建整个工作空间时，在工作空间根目录执行：

```bash
colcon build
```

编译完成不等于旧进程更新，必须重新启动。没有代码变化时不用每次构建。

## 3. 启动完整系统

2026-10-17持续避让更新需MPPI依赖，并更新运动/仿真/感知/导航四个包。
构建前退出旧系统。本机本次已安装依赖；换机器或后续修改时执行：

```bash
sudo apt-get install ros-jazzy-nav2-mppi-controller
cd /home/ma/lite3_ws
colcon build --packages-select lite3_control lite3_gazebo lite3_perception lite3_navigation
source /home/ma/lite3_ws/install/setup.bash
```

终端1准备环境后执行：

```bash
ros2 launch lite3_navigation bringup.launch.py
```

等待 `[Lite3 startup] READY` 和任务节点提示。它启动 Gazebo、Lite3、RViz、
地图、运动/桥接节点、Nav2 和已有 RL，并完成底层准备；**不自动发送目标，总开关默认关闭。**
不需要另开 RL、地图、规划器、控制器终端，也不需要手动按 z/c 或发布 external。

2026-10-17起默认controller=mppi、enable_replanning=true：局部控制允许绕开原路线，
受阻时自动等待/有限重规划。原RPP仍保留，回到旧单次规划行为时退出当前系统后用：

```bash
ros2 launch lite3_navigation bringup.launch.py controller:=rpp enable_replanning:=false
```

不要同时启动两个入口。更换控制器需重启；目标输入、角度单位、总开关命令不变。
默认地图/world仍是仓库。开发用world:=绝对SDF路径和map_yaml:=绝对yaml路径必须配套；
SDF的world名称仍须large_warehouse，坐标与map/odom保持一致。

当前入口的可选命令，按需要择一使用：

```bash
# 不打开两个图形窗口
ros2 launch lite3_navigation bringup.launch.py gui:=false rviz:=false

# 延长启动准备总等待时间，单位实际秒
ros2 launch lite3_navigation bringup.launch.py startup_timeout:=180

# 指定已有外部RL目录
ros2 launch lite3_navigation bringup.launch.py rl_dir:=/home/ma/Lite3_rl_deploy

# 只显示参数说明，不实际启动
ros2 launch lite3_navigation bringup.launch.py --show-args
```

不要同时运行两套完整入口。UDP端口或同一ROS域项目节点被占用时，启动会拒绝重复运行。

## 4. 查询总开关和任务状态

终端2：

```bash
ros2 service call /lite3/get_navigation_state std_srvs/srv/Trigger '{}'
```

**只读查询，不启动、不解锁、不取消导航。** 外层 `success: true` 表示查询成功，
实际开关看 `message` 中的 `navigation_enabled`。

返回信息示例：

```json
{"navigation_enabled":false,"busy":false,"fault_latched":false,"switch_pending":false,"phase":"IDLE"}
```

| 字段 | 含义 |
|---|---|
| navigation_enabled | true允许新导航目标，false关闭两种目标入口 |
| busy | 是否有任务正在执行或正在清理 |
| fault_latched | 是否因清理无法确认而锁定故障、拒绝后续任务 |
| switch_pending | 总开关操作是否还没结束 |
| phase | IDLE空闲；PLANNING规划；FOLLOWING行走；STOPPING停止清理；也可能是准备阶段 |

开关开启表示任务入口允许接收；RL状态、运动输入锁定等仍会影响实际行走。
**不要用开启命令当作查询命令，它会选择导航来源并请求解锁。**

查看最近一次运行说明：

```bash
# 查看最近一条，然后退出
ros2 topic echo /lite3/navigation_status --once --qos-durability transient_local

# 持续看后续进度和结果，Ctrl+C结束查看
ros2 topic echo /lite3/navigation_status --qos-durability transient_local
```

状态话题是运行事件文本，不能替代上面的实际开关查询。

## 5. 开启导航总开关

```bash
ros2 service call /lite3/set_navigation_enabled std_srvs/srv/SetBool '{data: true}'
```

等待 `success: true`。它确认系统可用、无旧任务，然后选择导航控制并显式解除停止锁定。
成功后既能用 Gazebo 新选点，也能用终端发目标。

- 初次启动默认关闭。
- 成功到达后保持开启，可继续发下个目标。
- 导航失败、取消、超时经过停止清理后关闭，需要用户重新开启。
- 纯非法数字/角度在提交或任务起始校验时被拒绝，不会因此关闭。
- 空闲多久不会自动关闭。
- 忙碌或清理故障时不能借重新开启覆盖旧任务。

## 6. 发送目标与返回出发点

### 6.1 简短命令：X、Y、到达角度

先开启总开关，再执行：

```bash
ros2 run lite3_navigation navigate 4 4 90
```

含义：去 map 中 `(4,4)`，到达朝向为 `90度`。坐标单位米。
`navigate` 默认角度单位是**度数**，范围 `[-180,180]`；0朝向地图X正方向，
90朝向Y正方向。命令会等待任务结束，并显示阶段、剩余距离和结果。

需要用弧度时：

```bash
ros2 run lite3_navigation navigate 4 4 1.5708 --radians
```

弧度范围 `[-pi,pi]`。示例目标不是所有情况下都能到达，需要地图和路线可通行。

### 6.2 Gazebo选点立即导航

这部分不需要额外终端目标命令：

1. 开启总开关。
2. 在 Gazebo 的“Lite3目标选点”面板点击“选择目标”。
3. 单击空闲地面，新点击立即提交任务；当前默认到达朝向为0弧度。
4. 接收、行走和错误信息在终端1或导航状态话题查看。

重新选点先再次按“选择目标”。拖动视角不选点。
面板关闭后，可在 Gazebo 右上角插件菜单找 `Lite3TargetPicker` 重新添加。

关闭期间可以选点预览，但开启后必须重新选点。
忙碌时新点击不覆盖当前任务、不排队；重复发布同一点击不会重复执行。
橙色标记表示最后点击位置，不代表任务已被接受或正在执行。

只读查看最后点击坐标：

```bash
ros2 topic echo /lite3/selected_goal --once
```

这是 `PoseStamped`，不是开始任务命令；查询不会再次提交目标。
这里的时间戳用于点击去重，不能当作机器人状态的仿真时间使用。

### 6.3 原Action入口：朝向使用弧度

```bash
ros2 action send_goal /navigate_task lite3_interfaces/action/NavigateTask \
  '{goal_x: 4.0, goal_y: 4.0, goal_yaw: 0.0}' --feedback
```

`goal_x/goal_y` 是map坐标，`goal_yaw` 是**弧度**，`--feedback` 显示过程反馈。
这与简短命令共用任务节点；不是两个独立导航系统。

### 6.4 返回出发点

把出发点作为新的目标，不需要另一种导航接口。
以下仅示例回到本项目当前默认出生点附近；不能当作任意运行的自动记录“家”：

```bash
ros2 run lite3_navigation navigate -4 -4 0
```

如实际出发点不同，用实际记录的坐标替换。默认从机器狗当前实际位置出发，
不需要每次填写起点。

### 6.5 可选起点一致性检查

只有想检查“我认为的起点是否与实际位置一致”时才使用：

```bash
ros2 action send_goal /navigate_task lite3_interfaces/action/NavigateTask \
  '{goal_x: 4.0, goal_y: 4.0, goal_yaw: 0.0, check_start: true, start_x: -4.0, start_y: -4.0, start_yaw: 0.0}' --feedback
```

起点朝向同样用弧度。不一致返回结果4。
这只做检查，**不会传送机器人、修改真实位置或重置仿真**。
默认 `check_start=false`，普通 `navigate` 不要求这一步。

## 7. 停止、取消与重新开启

### 7.1 推荐：关闭总开关，协调取消和停止

```bash
ros2 service call /lite3/set_navigation_enabled std_srvs/srv/SetBool '{data: false}'
```

同时适用于 Gazebo 和终端任务。立即禁止新目标，请求取消当前任务、锁定运动输入，
并等待清理确认。`success:true` 说明本层停止和清理已确认，不等于物理上瞬时停车。

重新使用导航前，确认任务清理完成，再显式开启总开关。
如果显示清理故障，不直接解锁去继续旧任务。

### 7.2 标准Action取消：针对终端Action任务

```bash
ros2 service call /navigate_task/_action/cancel_goal action_msgs/srv/CancelGoal '{}'
```

空请求取消该服务端可取消的Action目标；当前一次仅允许一个任务。
接受取消请求不等于任务已经清理结束，继续看结果/状态。

**Gazebo选点是在同一任务节点内部执行，没有终端Action目标句柄；
取消Gazebo任务用总开关关闭命令。**

### 7.3 直接锁定运动输入

```bash
ros2 service call /lite3/set_stop std_srvs/srv/SetBool '{data: true}'
```

这是运动节点的锁定，拒绝手动和导航速度。它本身不取消任务、不改变任务总开关，
所以日常导航取消优先用7.1。

只有确认旧任务已结束、确实要恢复相应控制模式时，才使用直接解锁：

```bash
ros2 service call /lite3/set_stop std_srvs/srv/SetBool '{data: false}'
```

继续导航时通常直接重新开启总开关即可，不需要另发这一条。
解锁不会复活保存的旧速度，但持续发布者发来的下一条消息仍可能驱动机器人。

## 8. 手动速度和键盘控制

### 8.1 从导航切到手动

按顺序分别执行，确认每条返回成功：

```bash
# 结束导航并关闭新目标入口
ros2 service call /lite3/set_navigation_enabled std_srvs/srv/SetBool '{data: false}'

# 选择手动速度来源
ros2 service call /lite3/set_navigation_mode std_srvs/srv/SetBool '{data: false}'

# 明确恢复手动输入
ros2 service call /lite3/set_stop std_srvs/srv/SetBool '{data: false}'
```

这里的三个接口含义不同：总开关管理任务，模式选择速度来源，停止锁定管理运动输入。
进入手动不需要开启导航总开关。

### 8.2 用终端持续发布速度

前进示例，持续运行直到 `Ctrl+C`：

```bash
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist \
  '{linear: {x: 0.32, y: 0.0}, angular: {z: 0.0}}' --rate 20
```

原地左转示例（先结束上一个发布者，再执行）：

```bash
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist \
  '{linear: {x: 0.0, y: 0.0}, angular: {z: 0.6}}' --rate 20
```

| 分量 | 含义与单位 |
|---|---|
| linear.x | 前后速度，m/s，正数向前 |
| linear.y | 左右侧向速度，m/s，正数向左；实际能力取决RL |
| angular.z | 转向速度，rad/s，正数左转 |

`--rate 20` 每秒发20条消息。它会持续发布，不会因为你不再打字就结束。
停发约0.5秒后运动节点目标速度归零；需要锁定停止时用7.3。

先退出持续发布者后，可发送一次零速度：

```bash
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist \
  '{linear: {x: 0.0, y: 0.0}, angular: {z: 0.0}}' --once
```

零速度消息不是锁定；仍在运行的发布者可用后续非零消息覆盖它。

### 8.3 键盘控制

本机已安装 `teleop_twist_keyboard`，完成手动准备后执行：

```bash
ros2 run teleop_twist_keyboard teleop_twist_keyboard --ros-args \
  -p speed:=0.32 -p turn:=0.6 -p stamped:=false
```

焦点放在运行这条命令的终端。当前标准工具的按键是：

| 按键 | 作用 |
|---|---|
| i | 前进 |
| , | 后退 |
| j / l | 左转 / 右转 |
| u / o | 前进并左转 / 右转 |
| k | 发零速度 |
| q / z | 同时增大 / 减小线速度和转向速度 |
| w / x | 增大 / 减小线速度 |
| e / c | 增大 / 减小转向速度 |
| Ctrl+C | 退出键盘程序，尽力发送零速度 |

**这里不是WASD按键布局，w是调速度。**
程序收到按键才发送消息，可按住方向键由键盘重复输入维持运动；
没有新输入约0.5秒后，运动节点目标速度归零。点按k主动发零速度更明确。
反复减速可能进入当前RL响应弱的低速范围；速度数值不等于实际速度精确跟踪。

新电脑如未安装该工具：

```bash
sudo apt install ros-jazzy-teleop-twist-keyboard
```

### 8.4 从手动回到导航

先停止并退出手动发布者/键盘程序，再开启导航总开关：

```bash
ros2 service call /lite3/set_navigation_enabled std_srvs/srv/SetBool '{data: true}'
```

它会选择导航来源并清除旧速度，之后再发目标。
不要向 `/nav_cmd_vel` 手动写入速度，避免争用控制器输出。

## 9. 查看位置、消息和通信接口

### 9.1 三维雷达、平地过滤与二维障碍地图（2026-10-14）

更新后先退出旧系统、按第2节构建，再由终端1按第3节启动。终端2source环境后查询。
完整bringup命令不变，自动启动新增的lite3_pointcloud_obstacles感知节点。
首次先保持站立、不开导航总开关，核对地面和障碍分类。

```bash
ros2 topic info /lite3/lidar/points --verbose
ros2 topic echo /lite3/lidar/points --field header --once --qos-reliability best_effort
ros2 topic echo /lite3/perception/status --once
ros2 topic echo /scan --field header --once --qos-reliability best_effort
ros2 topic hz /lite3/lidar/points --use-sim-time
ros2 run tf2_ros tf2_echo TORSO lidar_link
```

逐条运行：info/echo --once自动结束，hz/tf2_echo用Ctrl+C结束查看程序。
原始点云是sensor_msgs/msg/PointCloud2，bridge发布，720×31采样位置，lidar_link，
水平360°、垂直-60°～+30°，标称10Hz仿真时间，0.12～12米。
雷达安装在TORSO前方0.30米/上方0.15米；BEST_EFFORT是传感器QoS。
status输出有效点、障碍、地面、清除点数量及flat_ground模式。
**/scan已变为感知节点生成的二维障碍投影，坐标base_footprint、720方向，
不是原始雷达的单层扫描。** inf是该方向没有投影到有效障碍，不等于整段空间已确认安全。

RViz完整入口：橙红色Lite3 Obstacle Projection显示/scan；
Local Obstacle Costmap显示机器狗附近实时障碍及安全余量，Global Obstacle Costmap可勾选。
勾选Ground Points显示绿色地面点；勾选3D Obstacles显示保留高度的橙红障碍点云，
从侧面看能区分高度，不要把这一层与已投影到地面的/scan混淆。
原Warehouse Map仍是预制地图，不会因为雷达扫描就改写磁盘文件。

```bash
ros2 topic info /lite3/perception/obstacles --verbose
ros2 topic info /local_costmap/costmap --verbose
ros2 topic info /global_costmap/costmap --verbose
python3 /home/ma/lite3_ws/src/lite3_gazebo/test/check_scan.py
```

前三条确认接口/订阅，最后是最多30秒的只读点云与投影TF检查。
当前地板顶面z=0.005米，容差0.02米，障碍候选高度(0.025,0.65]米；
转换到odom之后过滤，补偿机身倾斜。地面有效回波保留用于清除旧障碍，自己不标成障碍。
当前只适用于平地；尚无起伏地面分割或SLAM。任务自动重规划见第10节。

需要独立站立调试时，退出完整系统后运行（不与bringup并行）：

```bash
ros2 launch lite3_gazebo simulation.launch.py paused:=false
```

此入口有传感器/过滤/投影，但不启动Nav2服务器或RL。原模型RViz布局需手动Add→
LaserScan(/scan)、PointCloud2(/lite3/perception/ground或obstacles)，QoS选择Best Effort。
暂停时不再更新扫描，先恢复播放；用Ctrl+C退出启动终端。
配置细节见[感知包说明](../src/lite3_perception/README.md)。

### 9.2 位置与其他接口

只读查看一次实际位置、关节和仿真时间：

```bash
ros2 topic echo /odom --once
ros2 topic echo /joint_states --once
ros2 topic echo /clock --once
```

`/odom` 的x/y为当前平面位置，姿态是四元数，不能把orientation.z直接当角度。
`/joint_states` 是Gazebo实际关节；`/clock` 是仿真时间。

持续查看地图中的机器人位置关系：

```bash
ros2 run tf2_ros tf2_echo map base_footprint
```

持续查看机身完整位置/姿态：

```bash
ros2 run tf2_ros tf2_echo odom TORSO
```

Ctrl+C仅结束这两个查看程序。

查看节点、话题、服务与Action：

```bash
ros2 node list
ros2 topic list
ros2 service list
ros2 action list
ros2 node info /mission_manager
ros2 action info /navigate_task
```

查看发布者、订阅者和消息类型：

```bash
ros2 topic info /cmd_vel --verbose
ros2 topic info /nav_cmd_vel --verbose
ros2 topic info /lite3/selected_goal --verbose
ros2 topic info /map --verbose
ros2 topic info /plan --verbose
```

查看输入消息格式：

```bash
ros2 interface show lite3_interfaces/action/NavigateTask
ros2 interface show geometry_msgs/msg/Twist
```

以上命令都不会发导航目标。

| 主要接口 | 类型 | 来源→接收者 / 用途 |
|---|---|---|
| /lite3/set_navigation_enabled | SetBool服务 | 终端→任务节点，开启/关闭总开关 |
| /lite3/get_navigation_state | Trigger服务 | 终端查询任务节点实际状态 |
| /navigate_task | NavigateTask Action | 终端→任务节点，目标/反馈/结果 |
| /lite3/selected_goal | PoseStamped话题 | GUI经现有桥接→任务节点，新选点 |
| /lite3/navigation_status | String话题 | 任务节点→查看终端，最近运行信息 |
| /lite3/set_navigation_mode | SetBool服务 | 选择运动节点的导航/手动来源 |
| /lite3/set_stop | SetBool服务 | 锁定/解除运动输入 |
| /cmd_vel | Twist话题 | 手动程序→运动节点 |
| /nav_cmd_vel | Twist话题 | Nav2控制器→运动节点 |
| /odom | Odometry话题 | 运动节点→Nav2及观察工具 |
| /joint_states | JointState话题 | Gazebo经桥接→模型状态发布器 |
| /lite3/lidar/points | PointCloud2话题 | Gazebo三维雷达经bridge→感知节点 |
| /lite3/perception/obstacles | PointCloud2话题 | 感知节点→全局/局部costmap体素层，障碍标记 |
| /lite3/perception/clearing | PointCloud2话题 | 感知节点→costmap体素层，三维射线清除 |
| /scan | LaserScan话题 | 感知节点→RViz/终端，二维障碍投影；SLAM待验证接入 |
| /map | OccupancyGrid话题 | 地图服务器→Nav2/RViz |
| /plan | Path话题 | 规划器→RViz，显示路线 |
| /clock | Clock话题 | Gazebo经桥接→仿真时间节点 |

### 9.3 添加原地图中没有的测试箱子（2026-10-17）

前置条件：终端1保持完整bringup运行，仿真播放；终端2已source环境。
先关闭导航并确认成功，保持机器狗站立，不在当前执行路径中突然放物体。

```bash
ros2 service call /lite3/set_navigation_enabled std_srvs/srv/SetBool '{data: false}'
```

以下命令只向正在运行的Gazebo场景加入一个静态箱子，不会改写原地图或自动开始导航：

```bash
gz service -s /world/large_warehouse/create \
  --reqtype gz.msgs.EntityFactory --reptype gz.msgs.Boolean --timeout 3000 \
  --req 'sdf_filename: "/home/ma/lite3_ws/src/lite3_gazebo/worlds/lidar_test_box.sdf"'
```

箱子名lite3_demo_box，中心(-2.25,1.79)，底面贴地，尺寸0.3×0.3×0.4米。
此处是地图/world中的固定坐标，不是“永远位于机器人前方”。2026-10-17只读检查时，
机器狗约(-3.255,1.787)，该位置在其附近原地图的空白区域。
若机器人移动到其他地方，先核对位置，避免箱子与机器狗重叠或位于雷达不可见处。
data:true表示生成请求成功；再检查Gazebo实体树lite3_demo_box及RViz实际变化。
若重复添加同名模型可能返回false，先按下面的移除命令清理，再重试。

预期：Gazebo出现橙色箱子；雷达点/障碍投影出现；勾选Global Obstacle Costmap、
Local Obstacle Costmap观察新增障碍及膨胀圈。局部图只有机器人附近4×4米范围，
箱子超出时用全局图检查。Warehouse Map保持原样，因为原地图没有该箱子。
这一步先验收感知，不等于已验收绕行。接着再选有绕行空间的目标测试新规划。

用户确认箱子出现后，2026-10-17只读复查机器狗约(-1.232,-2.407)，总开关false、任务IDLE。
ComputePathToPose预览到(-3.25,1.79)成功：193点、约5.10米，路径点距箱子中心最近约0.946米。
仅预览未执行FollowPath；此路线没有与无箱子场景对照，不能单独证明“因箱子而改变路线”。
保持箱子和仿真运行，在终端2逐条执行（首条success:true后再发目标）：

```bash
ros2 service call /lite3/set_navigation_enabled std_srvs/srv/SetBool '{data: true}'
ros2 run lite3_navigation navigate -3.25 1.79 90
```

目标X/Y单位米，90是最终朝向的度数；这两个命令会真正启动运动。仅用于上述位置条件，
机器人后来换位置应重新检查路线。观察全局图、路线及实际行走，成功以终端任务结果为准。
需要中止时，在另一已source终端关闭导航总开关；不要仅关闭CLI：

```bash
ros2 service call /lite3/set_navigation_enabled std_srvs/srv/SetBool '{data: false}'
```

这是“新箱子已存在，再规划并行走”的测试，不是行走中放入障碍后的自动重规划。
失败先保留错误信息，不反复解锁重试。

移除本次测试箱子（不会删除货架或机器狗）：

```bash
gz service -s /world/large_warehouse/remove \
  --reqtype gz.msgs.Entity --reptype gz.msgs.Boolean --timeout 3000 \
  --req 'name: "lite3_demo_box", type: MODEL'
```

等待雷达重新扫到对应空间，观察实时障碍清除；遮挡范围内不能保证立即清除。
服务命令完成后自动退出终端，无需Ctrl+C；模型文件在src，当前无需重新编译。
主world没有include此模型，重启不会自动放入箱子；它是可重复手动验收资源。

## 10. 查看速度参数和错误含义

### 持续避让与任务恢复（2026-10-17）

默认MPPI在controller_server内部比较局部走法，仍经/nav_cmd_vel→运动节点→RL执行。
当前FollowPath.plugin实际为lite3_navigation::AvoidanceController：途中调用原生MPPI，
最后0.65米复用原生RPP接近与原地转向，共用碰撞检查；不是新增节点或第二个速度发布者。
无需新增常驻节点。反馈中可能看到RECOVERY_STOPPING、WAITING_OBSTACLE、REPLANNING、
RECOVERY_RESUMING，表示任务仍在执行，不需要重新发送目标。
局部控制104/105/106，或连续3实际秒既未移动10cm也未转动0.20rad（约11.5°），会触发恢复。
首次等待0.5实际秒；同一受阻窗口内连续重规划仍无路时，等待按0.5→1→2→2秒退避。
恢复行走后再次受阻，首次等待重新从0.5秒开始；全任务最多5次重规划，受阻窗口25秒、任务120秒。
MPPI连续无法给出可行控制的容忍时间从1.5缩到0.5秒（controller_server仿真时钟）；实际响应还包括取消确认和计算时间。
配置在config/mission.yaml与controller_mppi.yaml，不保证每个场景都在固定时间内绕过。
replan_count/retry_count现在记录实际次数；初次没有路线返回1，恢复预算耗尽返回2。
2表示未恢复可执行运动，可能是障碍/轮廓/运动响应，不是物理接触或跌倒证明。

内部/lite3/set_navigation_pause是SetBool服务，true暂停导航并清零，false只解除内部暂停；
不会解除用户/lite3/set_stop锁定，也不阻挡手动模式。日常不需要手动调用，
任务管理节点协调它。用户要结束任务仍使用总开关false，不能用内部暂停代替取消。
用户取消、总开关关闭、系统故障都优先于自动恢复，失败后仍需显式重新开启导航。
现有感知节点还会根据连续雷达观测估计紧凑物体的移动方向和速度，预留未来2.5仿真秒
可能经过的区域；这不是物体识别或完整多目标跟踪，也未实现SLAM。

在空闲且已source的终端2只读查看估计（Ctrl+C退出，不影响任务）：

```bash
ros2 topic echo /lite3/perception/status
ros2 topic hz /lite3/perception/forecast
```

第一条显示JSON计数和moving_clusters中的odom中心坐标（米）/速度（米每秒）；
第二条单独运行，只检查预测PointCloud2的发布频率，空预测帧也正常发布。
预测不是原始雷达点，不能把它用于射线清除。空观测或超时会从代价层中移除旧预测。
更改/home/ma/lite3_ws/src/lite3_perception/config/flat_ground.yaml中的
forecast_enabled、forecast_horizon（仿真秒，默认2.5）、forecast_padding（米，默认0.10）
后需退出旧系统、构建lite3_perception、重新source并重启。
关闭预测仅保留实测障碍反应，横穿物体可能再次擦碰；细节见CONTINUOUS_AVOIDANCE。

### 加入持续运动的实体箱子（2026-10-17）

终端1保持新版bringup；终端2已source。模型不会自动加入。先检查投放位置和运动
走廊不与机器狗/货架重叠。以下坐标是空地验收示例，仓库中请按实际通道修改，
不是永远位于机器狗前方；模拟盒子会真实碰撞，默认没有自己的避障算法。

```bash
ros2 run lite3_navigation moving_obstacle --x -1.8 --y -4.6 --vx 0 --vy 0.18 --seconds 6 --remove
```

X/Y单位米，VX/VY米每秒（初始朝向为0）；seconds为实际秒，仿真暂停仍计时。
创建lite3_dynamic_box，匀速移动，结束/此终端Ctrl+C发送箱子零速度；--remove移除本次箱子。
不带--remove则结束后箱子保留并停车。同名箱子已存在会报错，不覆盖或重置它。
此命令只驱动箱子，不发布机器狗/cmd_vel，不直接修改地图，不直接开始导航。
机器狗的导航目标仍由原navigate或Gazebo点击发送；总开关需要开启。
工具运行占用终端2，需要同时发命令时另开一个已source终端。

手动让箱子停止/移除的备用命令（只针对lite3_dynamic_box）：

```bash
gz topic -t /lite3/dynamic_box/cmd_vel -m gz.msgs.Twist -p 'linear: {x: 0, y: 0}'
gz service -s /world/large_warehouse/remove --reqtype gz.msgs.Entity --reptype gz.msgs.Boolean --timeout 3000 --req 'name: "lite3_dynamic_box", type: MODEL'
```

第一次从低速单物体开始。验收需观察雷达、costmap更新/清除、实际运动和任务结果；
不能只看到地图上有箱子就称为避障通过。

### 10.1 青色碰撞区域与导航轮廓（2026-10-17）

全局/局部costmap当前使用用户指定约20cm青圈的仿真调试值：0.80×0.36米矩形，
footprint_padding=0.02米/侧；实际检查外沿为x=±0.42、y=±0.20米。
内切半径约0.20米，因此青色区域缩小；不是把整个机器人缩成半径0.20米圆。
同日较早的矩形宽0.56米/内切半径0.30米配置已被此配置替代。
外围inflation_radius=0.6和cost_scaling_factor=3.0保持；速度/RL/雷达/停止逻辑保持。
当前站姿碰撞投影宽约0.375米，总宽0.40米只多约0.025米，侧向余量很小。
此配置不能视为已验证的完整步态外沿，行走/转向可能擦碰，需实际仿真验收。
以下为较早NavFn配置说明，现默认Lattice已在规划时检查朝向轮廓；旧NavFn仅按二维代价规划，RPP会检查矩形碰撞，
无法转身的通道仍应停车，不能把缩圈视作所有窄通道必能通行。

本机已构建安装导航包；旧运行进程不会自动采用新配置。
终端2先关闭总开关，确认成功、任务退出；终端1按Ctrl+C退出整套bringup。

```bash
ros2 service call /lite3/set_navigation_enabled std_srvs/srv/SetBool '{data: false}'
```

终端1重新启动（新终端先按第1节source）：

```bash
source /opt/ros/jazzy/setup.bash
source /home/ma/lite3_ws/install/setup.bash
ros2 launch lite3_navigation bringup.launch.py
```

等待READY后，在终端2只读核对新参数；应为四个±0.40/±0.18顶点及padding=0.02：

```bash
ros2 param get /global_costmap/global_costmap footprint
ros2 param get /local_costmap/local_costmap footprint
ros2 param get /local_costmap/local_costmap footprint_padding
ros2 topic echo /local_costmap/published_footprint --once
```

published_footprint是变换到odom的实际检查外沿，不是原始局部顶点，转向后坐标会变。
RViz勾选全局/局部costmap查看青圈；按第5/6节显式开启并发新目标后才会行走。
重启会移除先前手动添加的箱子，需要时按9.3重新加入，先核对新起点与箱子不重叠。
仍发生104时保留日志，检查实际转弯/障碍，不关闭碰撞检查强行通过。

隔离验证工具仅供开发调试，不是日常启动命令；专用ROS域196，
不启动Gazebo/RL/运动节点，以合成地图和真实Nav2检查横向通过与碰撞拦截：

```bash
ROS_DOMAIN_ID=196 python3 /home/ma/lite3_ws/src/lite3_navigation/test/check_navigation_footprint.py
```

以下是原有速度参数和错误说明。

默认MPPI只读查询当前控制器参数：

```bash
ros2 param get /controller_server FollowPath.plugin
ros2 param get /controller_server FollowPath.vx_max
ros2 param get /controller_server FollowPath.wz_max
ros2 param get /mission_manager max_replans
ros2 param get /mission_manager stuck_timeout
ros2 param get /mission_manager replan_wait
ros2 param get /mission_manager replan_wait_max
```

MPPI参数文件为/home/ma/lite3_ws/src/lite3_navigation/config/controller_mppi.yaml；
vx_max为前进上限、wz_max为转向上限，实际RL响应可能不同。
回退到RPP时才使用controller.yaml及以下参数名：

```bash
ros2 param get /controller_server FollowPath.desired_linear_vel
ros2 param get /controller_server FollowPath.rotate_to_heading_angular_vel
ros2 param get /controller_server failure_tolerance
```

修改导航默认速度的文件为
`/home/ma/lite3_ws/src/lite3_navigation/config/controller.yaml`。
`desired_linear_vel` 是期望前进速度，`rotate_to_heading_angular_vel` 是转向速度。
编辑后按第2节构建导航包并重启；不是修改终端目标中的角度来调速度。
具体速度配置按当前文件为准，本手册不固定替换用户已调整的数值。

| 结果 / 信息 | 含义 |
|---|---|
| RESULT 0 | 成功到达并通过最终位姿检查 |
| RESULT 1 | 没有有效全局路径 |
| RESULT 2 | 自动恢复预算耗尽，未恢复可执行运动；结合日志判断障碍或运动约束 |
| RESULT 3 | 非法数字/角度、地图外目标或目标占据区 |
| RESULT 4 | 用户要求检查的起点与实际位置不一致 |
| RESULT 6 | 任务总预算超时 |
| RESULT 7 | 任务取消；同时看说明和Action状态 |
| RESULT 8 | 系统/跟随/清理错误，或关闭总开关时提交目标；看具体message |
| NAVIGATION_DISABLED | 总开关关闭，需按需显式开启 |
| BUSY / BUSY_OR_FAULT | 有旧任务、开关操作或清理故障，不覆盖它 |
| Nav2码104 | 控制器连续无法产生可执行速度，超过允许等待时间 |
| Nav2码105 | 机器人未在规定时间内取得足够位置进展 |

任务结果编号与Nav2错误码是两层，不能混用。
结果2（BLOCKED）现在用于有限恢复耗尽；结果5（MOTION_FAILED）的跌倒分类仍未实现。

2026-10-13实际104案例：输入已成功规划77点，但控制器连续
`detected collision ahead!`，在 `failure_tolerance=0.3` 秒后退出。
这是已有地图/碰撞预测的判断，具体几何原因还需检查；不是激光检测到临时障碍。
该案例发生在雷达接入之前；现在已接三维感知和实时costmap，104也可能与新障碍有关，
需结合当前地图/扫描及控制器日志判断。2026-10-17起默认有限自动恢复已接入，
104/105/106可先等待/重规划；关闭enable_replanning时仍沿旧逻辑直接结束任务。
失败后总开关关闭、运动停止锁定，不会自动重试；提高等待时间本身不能解决几何冲突。

## 11. 正常退出

1. 在终端2关闭总开关，等待返回并确认清理结果。
2. 查询状态，正常情况下为 `navigation_enabled=false`、`busy=false`、
   `switch_pending=false`，没有清理故障；故障时先排查，不解锁继续旧任务。
3. 退出其他查看程序/手动发布者，在终端1按Ctrl+C，等待整套系统退出。
4. 终端窗口可以关闭；下次重新打开、source环境并启动。

运行 `navigate` 时Ctrl+C只退出客户端，不等于可靠取消。
可以先退出客户端，再在同一终端执行总开关关闭命令，或用另一个已source的终端关闭。

重启发现端口占用时，只读检查：

```bash
ss -lunp '( sport = :20001 or sport = :30010 or sport = :30011 )'
```

Gazebo包装进程退出时端口可能稍后释放；等待退出完成再启动。
不把未知进程直接批量杀掉，也不重复起另一套系统。

## 12. 单模块调试入口

**这是调试备用，不与完整bringup并行运行同一组件。**

只展示模型：

```bash
ros2 launch lite3_description display.launch.py
```

只启动Gazebo/模型/RViz/运动与桥接：

```bash
ros2 launch lite3_gazebo simulation.launch.py
```

这个入口默认暂停，不自动准备完整Nav2和RL。默认包含选点面板；
调试时可关闭自定义GUI布局：

```bash
ros2 launch lite3_gazebo simulation.launch.py target_picker:=false
```

只启动任务节点（需要已有地图、TF、Nav2和运动服务）：

```bash
ros2 run lite3_navigation mission_manager --ros-args \
  -p use_sim_time:=true -p task_timeout:=120.0
```

`task_timeout` 是任务总预算，单位实际秒。当前完整bringup不提供转发该参数的选项；
不要把这里的单节点参数误用成已支持的完整launch参数。
新节点默认关闭总开关，不带旧goal_x/goal_y启动参数自动跑任务。

只启动运动节点（不要重复占用UDP接口）：

```bash
ros2 run lite3_control lite3_motion_node
```

独立底层调试时，手动运行已有RL：

```bash
cd /home/ma/Lite3_rl_deploy/build
./rl_deploy --ros-velocity
```

RL终端按z、等待至少4秒、再按c，确认进入rl_control。
--ros-velocity下w/s/a/d等移动键禁用；空格锁定RL速度，RL控制状态下c解除该锁。
这是RL自己的锁，与ROS运动锁和任务总开关不同。
底层x/X、r调试不是任务取消或跌倒恢复；完整bringup已监管RL，不要再启动第二份。

独立调试时Gazebo控制接管：

```bash
gz topic -t /lite3/control_mode -m gz.msgs.StringMsg -p 'data: "external"'
gz topic -t /lite3/control_mode -m gz.msgs.StringMsg -p 'data: "stand"'
```

两条分别为外部RL接管、固定站立回退，按需要择一，不连续执行来展示移动。
这是Gazebo Transport话题，不是ROS2话题。
固定站立不是倒地自主起身；不要同时运行MuJoCo接收器争用相同UDP端口。
完整启动及依赖恢复仍见[RUNBOOK](RUNBOOK.md)和[外部RL说明](../external/lite3_rl_deploy/README.md)。

## 13. 常用操作速查表

先source环境；表中命令仅在相应节点运行且接口已安装时可用。

| 想做什么 | 命令 |
|---|---|
| 启动全部 | `ros2 launch lite3_navigation bringup.launch.py` |
| 查总开关/任务 | `ros2 service call /lite3/get_navigation_state std_srvs/srv/Trigger '{}'` |
| 开启导航 | `ros2 service call /lite3/set_navigation_enabled std_srvs/srv/SetBool '{data: true}'` |
| 发X/Y/度数 | `ros2 run lite3_navigation navigate 4 4 90` |
| 停止并取消当前导航 | `ros2 service call /lite3/set_navigation_enabled std_srvs/srv/SetBool '{data: false}'` |
| 看导航运行信息 | `ros2 topic echo /lite3/navigation_status --qos-durability transient_local` |
| 看当前实际位置 | `ros2 topic echo /odom --once` |
| 看投影坐标名 | `ros2 topic echo /scan --field header --once --qos-reliability best_effort` |
| 看最后选点 | `ros2 topic echo /lite3/selected_goal --once` |
| 锁定所有ROS速度输入 | `ros2 service call /lite3/set_stop std_srvs/srv/SetBool '{data: true}'` |
| 键盘手动移动 | 先完成8.1，再执行8.3，使用i/j/k/l等键 |
| 退出系统 | 先关闭导航并确认，再在启动终端Ctrl+C |

## 14. 维护与更新记录

本文只列当前已存在的接口和命令；未实现功能不能写成可用操作。
后续每次修改终端交互、服务/Action/话题、角度单位、参数或停止逻辑，
在同一次开发中同步核对本文，并更新日期和下表。源码有变化需要构建/重启时必须说明。

| 日期 | 更新 |
|---|---|
| 2026-10-17 | 缩短受阻反应：无有效运动3秒、首次等待0.5秒、持续无路最多退避至2秒；转向也算进展；MPPI失败容忍0.5秒，需重启生效 |
| 2026-10-17 | 持续避让：默认MPPI/原RPP回退；内部暂停与用户停止分离，等待/有限重规划；雷达短期运动估计/独立预测层；反馈次数、结果2、移动箱子工具、新依赖/构建/参数说明 |
| 2026-10-17 | 新增手动测试箱子、路线预览说明；两图矩形轮廓缩圈后按用户要求进一步调到20cm（含padding总宽40cm），补重启/参数核对/隔离测试和小余量限制；修正旧104历史措辞 |
| 2026-10-13 | 按实际源码统一整理日常启动、总开关、只读查询、双目标入口、手动/键盘、取消、退出、调试与错误说明；加入持续维护约定 |
| 2026-10-14 | 升级三维点云；新增平地感知/地面与自身过滤；全局局部体素层投影和清除；更新/scan为base_footprint障碍投影、验收和构建命令 |
| 2026-10-13 | 接入二维模拟雷达/scan、lidar_link TF与导航RViz扫描显示；补充构建、只读验收和独立扫描检查命令，注明障碍层/SLAM尚未接入 |

接口实现细节与验证记录见[NAVIGATION_INTERACTION](NAVIGATION_INTERACTION.md)；
最新开发接续见[SESSION_HANDOFF](SESSION_HANDOFF.md)。日常复制命令优先使用本文。

2026-10-17补充：完整轮廓Lattice/MPPI后退、失败路段软代价、执行路线与状态显示、last_result查询和错误分类，见本文顶部。
