# Lite3 导航任务节点

**2026-10-17 完整轮廓与受阻优化（当前版本）：** 默认全局规划改为Smac Lattice，
在5cm地图上结合机身朝向和0.84×0.40m矩形检查路线；MPPI允许必要的短距离后退（最低-0.30m/s）。
受阻恢复增加近期失败路段软代价，促使有替代路线时换路；不把失败路段当作真实障碍。
RViz只默认显示当前接受执行的路线，结束/恢复清空，并显示任务状态；状态查询保留最后结果。
总开关、任务Action、20cm内切半径、RL和原整体规划保持；未新增常驻节点。
操作、回退、错误及新增话题见[终端手册](../../docs/TERMINAL_COMMANDS.md)顶部，
本轮证据和限制见[完整轮廓优化记录](../../docs/FOOTPRINT_REPLANNING.md)。较早NavFn说明为历史阶段。


## 2026-10-17持续避让入口

反应时间后续调优：3实际秒无10cm平移或0.20rad转向才判无进展；首次恢复等0.5秒，
连续无路时等待递增至最多2秒，恢复运动后新受阻窗口重置。MPPI控制失败容忍0.5仿真秒。

默认完整bringup使用controller_mppi.yaml；controller.yaml保留RPP。
任务受阻支持内部暂停/等待/有限重规划，Action反馈replan_count、结果retry_count真实计数。
内部暂停不解除用户停止锁定，用户取消/总开关关闭仍终止任务。
配置/限制见[持续避让说明](../../docs/CONTINUOUS_AVOIDANCE.md)，
命令以[终端手册](../../docs/TERMINAL_COMMANDS.md)为准，实际验证见SESSION_HANDOFF。
下方带日期的较早验收为历史记录，当前功能以本节和终端手册为准。

## 最新交互（2026-10-13）

任务节点新增 `/lite3/set_navigation_enabled` 总开关（默认关闭）、Gazebo新选点入口和
`/lite3/navigation_status`。终端 `ros2 run lite3_navigation navigate X Y 角度` 默认度数；
原NavigateTask仍用弧度。两个入口共用任务状态机，无额外常驻节点。
先开启总开关才会执行目标；关闭协调取消/停止，失败清理后需要显式重新开启。
开启操作确认没有旧任务后选择导航并解除停止；普通目标本身仍不自动解锁。
忙碌点击不排队，重复选点消息只执行一次，开关重开不执行旧点。
应用更新/命令/错误分类见 [交互手册](../../docs/NAVIGATION_INTERACTION.md)。
以下旧Action命令必须先开启总开关。本机先隔离编译测试，重启并构建后才应用新版本。

## 完整系统简化启动（2026-10-12）

已新增 `ros2 launch lite3_navigation bringup.launch.py`。日常只需要两个终端：一个保持整套系统运行，另一个发送任务或检查状态。
它自动加载仓库、生成 Lite3、播放仿真、打开导航 RViz、启动运动/桥接/模型节点、加载安装目录中的地图、发布 map→odom、配置并激活 Nav2、准备已有 RL 程序，确认 Gazebo external 接管后再启动常驻 mission_manager。
不会自动发送导航目标。原来的单模块和多终端方式仍可调试，但不要与完整入口同时运行。

修改后首次构建（本机此次已完成）：

```bash
source /opt/ros/jazzy/setup.bash
cd /home/ma/lite3_ws
colcon build --packages-select lite3_description lite3_control lite3_gazebo lite3_perception lite3_navigation
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
ros2 service call /lite3/set_navigation_enabled std_srvs/srv/SetBool "{data: true}"
ros2 action send_goal /navigate_task lite3_interfaces/action/NavigateTask \
  '{goal_x: 4.0, goal_y: 4.0, goal_yaw: 0.0}' --feedback
```

取消、返回基地和模式切换仍使用已有接口，详见 TERMINAL_COMMANDS。取消/失败后先确认清理完成，再按需显式解除停止锁定，不由 launch 自动恢复旧任务。
退出时先取消并确认正在执行的任务结束，再在终端 1 按 Ctrl+C；launch 回收本次启动的组件和 RL。等待退出完成后再启动，Gazebo 包装进程退出时端口可能短暂延后释放。

可选参数：`gui:=false rviz:=false` 不打开窗口，`rl_dir:=/实际路径/Lite3_rl_deploy` 指定已有外部项目，`startup_timeout:=180` 延长启动总等待（实际秒）。
端口 20001/30010/30011 被占用时拒绝重复启动，不自动杀其他进程。初始暂停或反复重启导致启动失败时查看启动终端日志。
完整 RL 原始输出写入本次 ROS launch 日志目录的 `rl-deploy.log`。终端显示重要状态，不需要用户打开额外 RL 终端。
模型、地图、RL 权重、控制器速度、任务协议和未来规划均保持原样。


`mission_manager` 现在常驻，提供 `/navigate_task`（`lite3_interfaces/action/NavigateTask`）。
面对终端是 Action 服务端，面对 Nav2 是规划/跟随客户端；不增加常驻节点。
原来的单次启动参数程序完整保存在 `mission_manager_once.cpp`，可执行名为
`mission_manager_once`。两种入口择一运行，不能同时控制同一台机器狗。

## 当前已实现

- 一次只接收一个目标，忙碌时拒绝新目标；任务结束后继续等待。
- 以 map 中实际 TF 位姿为起点，直接把 ComputePathToPose 的完整 Path 交给 FollowPath。
- 反馈执行阶段、当前 map 位姿和控制器的剩余路线距离；未取得距离时为 NaN。
- 完成时返回任务结果编号、解释及最新可用的最终位姿；位姿不可用时 frame_id 为空，说明写入 message。
- 可选起点位置/朝向一致性检查；最终成功还需核对实际位置/朝向容差。
- 请求运动节点选择导航输入，不解除任何停止锁定。
- 取消和任务超时会请求锁定停止，并取消正在等待或执行的 Nav2 任务。
  必须确认停止服务成功、下游任务终止后才释放忙碌状态。
- 清理超时则返回 SYSTEM_ERROR 并拒绝后续任务；晚到的 Nav2 接受响应仍会触发取消。
  排查旧任务和停止状态后再重启任务节点，不自动解锁或偷偷覆盖旧路线。

成功到达后依赖现有控制器发送零速度，不额外锁定运动节点，可继续发下一次任务。
取消、失败、超时后停止锁定保持开启；下一次实际行走前需用户显式解除。
停止服务确认只表示运动节点已锁定输入，不是脚部稳定或实际瞬时停车的证明。

## 结果分类

| 编号 | 名称 | 当前触发条件 |
|---|---|---|
| 0 | SUCCESS | 控制器成功且最新 map 位姿在目标位置/朝向容差内 |
| 1 | NO_PATH | 规划器返回 NO_VALID_PATH |
| 3 | INVALID_GOAL | 无效数字、规划器报告目标在地图外/占据区 |
| 4 | START_MISMATCH | check_start=true 且填写起点不符合实际位姿 |
| 6 | TIMEOUT | 整个任务耗尽实际时间预算，且清理确认完成 |
| 7 | CANCELED | 用户取消且清理确认完成 |
| 8 | SYSTEM_ERROR | TF/服务/路线/控制器异常，或清理无法确认 |

2 BLOCKED用于有限恢复预算耗尽；5 MOTION_FAILED的跌倒分类仍未实现。
Nav2原始错误码保留在message中；104/105/106默认先触发暂停/等待/重规划，不能据此认定物理碰撞。
任务结果编号与 Action 的 SUCCEEDED/ABORTED/CANCELED 是不同字段。
用户取消但清理失败时，Action 状态为 CANCELED，任务 result_code 为 SYSTEM_ERROR，应看结果说明。
retry_count/replan_count现在按实际重规划次数累计；enable_replanning=false时沿原一次规划行为。

## 构建

```bash
source /opt/ros/jazzy/setup.bash
cd /home/ma/lite3_ws
colcon build --packages-up-to lite3_navigation
source /home/ma/lite3_ws/install/setup.bash
```

## 实际使用：启动与发任务分开

先按根 README 启动已有 Gazebo、RL、地图、TF、规划器和控制器，完成 z→等待→c 和 external 接管。
以下所有终端均需 source ROS2 和工作空间。任务节点不负责启动这些系统或检测 RL 是否在行走模式。

终端 A：启动任务节点，只有等待，不会自动行走。

```bash
source /opt/ros/jazzy/setup.bash
source /home/ma/lite3_ws/install/setup.bash
ros2 run lite3_navigation mission_manager --ros-args -p use_sim_time:=true
```

终端 B：在确认旧任务已结束后显式解除停止锁定，再发目标。发目标会实际行走。

```bash
source /opt/ros/jazzy/setup.bash
source /home/ma/lite3_ws/install/setup.bash
ros2 service call /lite3/set_stop std_srvs/srv/SetBool '{data: false}'
ros2 action send_goal /navigate_task lite3_interfaces/action/NavigateTask \
  '{goal_x: 4.0, goal_y: 4.0, goal_yaw: 0.0}' --feedback
```

目标属于 map；发送前读取实际位置，避免把已到达同一目标的立即成功当作新运动测试。
可选起点检查示例字段：`check_start: true, start_x: -4.0, start_y: -4.0, start_yaw: 0.0`；
起点只用于核对，不修改定位，不强迫规划器从错误位置出发。

终端 C：标准 Action 取消服务。空请求的 UUID/时间戳均为0，表示取消此入口的所有任务；
本节点最多只有一个任务。服务返回仅表示接受了取消请求，最终结果需看终端 B 或任务节点日志。

```bash
source /opt/ros/jazzy/setup.bash
source /home/ma/lite3_ws/install/setup.bash
ros2 service call /navigate_task/_action/cancel_goal action_msgs/srv/CancelGoal '{}'
```

取消后停止锁定保持开启。先确认结果说明旧任务已结束，再决定是否显式解锁并发新目标。
不要通过 Ctrl+C 关闭客户端来代替取消；关闭任务节点或进程异常退出也没有可靠的跨进程自动清理保证。
需要暂停前先取消任务并核对最终结果；紧急锁定输入仍用 `/lite3/set_stop` 的 data=true。
直接调用停止锁定服务只锁输入，没有通知任务管理器取消，需同时使用任务取消入口。

## 参数（正的有限数）

| 参数 | 默认 | 用途 |
|---|---|---|
| task_timeout | 120.0秒 | 整个任务预算，steady clock，不受暂停仿真影响 |
| server_timeout | 5.0秒 | 等待依赖/导航模式响应 |
| cleanup_timeout | 5.0秒 | 等待停止锁定及 Nav2 终止确认 |
| pose_max_age | 1.0秒 | TF最大年龄，按ROS时间判断 |
| start_xy_tolerance | 0.5米 | 可选起点位置偏差 |
| start_yaw_tolerance | 0.5弧度 | 可选起点朝向偏差 |
| goal_xy_tolerance | 0.25米 | 最终位置检查 |
| goal_yaw_tolerance | 0.25弧度 | 最终朝向检查 |

参数在启动时读取。任务超时后可能额外等待 cleanup_timeout 秒完成清理。
最终目标容差应与 controller.yaml 中 goal_checker 的配置保持一致。

## 保留旧入口

```bash
ros2 run lite3_navigation mission_manager_once --ros-args \
  -p use_sim_time:=true -p goal_x:=-3.2 -p goal_y:=-4.0 -p goal_yaw:=0.0
```

旧入口与之前单次程序行为一致，也保留了关闭客户端不会主动取消下游任务的限制。

## 隔离复测

```bash
source /opt/ros/jazzy/setup.bash
source /home/ma/lite3_ws/install/setup.bash
ROS_DOMAIN_ID=178 python3 /home/ma/lite3_ws/src/lite3_navigation/test/check_mission_manager.py
```

脚本拒绝使用默认域或已有其他节点的域；运行真实任务程序、模拟 Nav2/TF/停止服务。
不启动 Gazebo/RL，不发送 UDP 或真实速度。2026-10-10 的16项实际协议检查通过，
原证据 `/tmp/lite3-mission-action-jd16n1ih/result.json`，已持久归档到 [任务接口验证结果](../../docs/development_history/evidence/mission_action/result.json)。这不是新 Action 入口的真实 Gazebo 行走验收。

下一步由用户在现有仿真中验收新入口；后续完善 `/stop_task`、状态查询、
重新规划/受阻重试、跌倒处理、地图与生命周期管理，雷达仍后接。

### 本次实际验证（2026-10-12）

三包构建及新旧 launch 参数查询通过。在 ROS_DOMAIN_ID=180、独立 Gazebo 分区中实际启动无 GUI 完整系统：地图、规划器、控制器均 active（3）；地图224×224；12关节、map→TORSO TF、/navigate_task 服务端正常；就绪后临时 startup ROS 节点已销毁；运动/任务节点各一个，导航速度发布者一个。RL 自动 idle→standup→rl_control、ONNX ENTER，实际插件确认 external；默认零速下机器人稳定在约(-3.994,-4.000)。没有发送导航目标或非零速度，此验证不替代用户 GUI/新路线行走验收。
已发 SIGINT 结束此次 launch，自己的 RL 和节点退出，20001/30010/30011 全部释放；Gazebo 的 Ruby 包装进程由 launch 的 SIGTERM 超时回收机制结束。另验证 RL 文件缺失、UDP30011占用、同一ROS域遗留map_server均在启动组件之前拒绝，且不终止其他进程；空ROS域接受完整启动计划。
初次测试发现本机rclpy未提供qos_profile_clock，已改为明确的best-effort时钟QoS并构建、重新通过上述实际启动。无额外系统安装、无RL源码修改、无Git提交/推送。
