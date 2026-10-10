# Lite3 导航任务节点

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

2 BLOCKED、5 MOTION_FAILED 保留原接口定义，目前没有重规划重试和跌倒检测，不产生这两个结果。
Nav2 原始错误码保留在 message 中；例如控制器 105 目前归为 SYSTEM_ERROR，不能据此认定机器人被围住。
任务结果编号与 Action 的 SUCCEEDED/ABORTED/CANCELED 是不同字段。
用户取消但清理失败时，Action 状态为 CANCELED，任务 result_code 为 SYSTEM_ERROR，应看结果说明。
retry_count/replan_count 当前均为0。

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
