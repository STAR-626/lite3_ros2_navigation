# Lite3 导航任务接口

此包定义 `lite3_interfaces/action/NavigateTask`，是原规划中终端向
`mission_manager` 下达任务的数据格式。它不包含可执行节点，不增加常驻节点。

## 当前状态

已建立接口定义及构建配置；本机构建、`ros2 interface show` 及目标/反馈/结果的
实际序列化往返检查通过。`mission_manager` 已提供 `/navigate_task` Action 服务端，
支持持续接收任务、反馈/结果、取消清理、可选起点检查和总超时；隔离协议测试通过，
新入口的实际 Gazebo 行走仍需用户验收。详见 [导航节点说明](../lite3_navigation/README.md)。
字段和结果常量本身只定义数据格式；跌倒检测、受阻重试和重新规划尚未实现。

## 三部分数据

| 部分 | 主要字段 | 含义 |
|---|---|---|
| Goal | goal_x / goal_y / goal_yaw | map 中的目标，米和弧度 |
| Goal | check_start / start_x / start_y / start_yaw | 可选起点检查，默认关闭 |
| Result | result_code / message | 原架构的 0–8 任务结果编号及说明 |
| Result | final_pose / retry_count | 最终 map 位姿及重试次数 |
| Feedback | phase / current_pose | 执行阶段及当前 map 位姿 |
| Feedback | remaining_distance / replan_count | 剩余路线距离及重新规划次数 |

结果编号沿用原设计：0 SUCCESS、1 NO_PATH、2 BLOCKED、3 INVALID_GOAL、
4 START_MISMATCH、5 MOTION_FAILED、6 TIMEOUT、7 CANCELED、8 SYSTEM_ERROR。
这些编号不等于 Nav2 的错误码，也不等于 Action 自身的成功/取消/中止状态。
默认构造的结果字段并非一次任务的执行结果，不能将默认的零值视为已成功导航。
节点应填写实际位姿及时间戳，不能把默认构造的位置当成机器人真实位置。

## 构建和查看

```bash
source /opt/ros/jazzy/setup.bash
cd /home/ma/lite3_ws
colcon build --packages-select lite3_interfaces
source /home/ma/lite3_ws/install/setup.bash
ros2 interface show lite3_interfaces/action/NavigateTask
```

最后一条命令只打印格式，不下达导航任务，不需要 Gazebo 或 RL。

Action 服务端复用已有规划与跟随客户端；原架构、已验证的运动配置保持不变。
原单次启动参数入口保存为 `mission_manager_once`，两种入口择一运行。
