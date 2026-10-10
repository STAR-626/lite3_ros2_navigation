# 当前终端交互（用于操作与PPT）

以下以当前源码为准。除RL终端外，新ROS终端先执行：

```bash
source /opt/ros/jazzy/setup.bash
source /home/ma/lite3_ws/install/setup.bash
```

## 用户任务与运动操作

| 操作 | 接口 | 通信方式 |
|---|---|---|
| 输入目标/朝向 | /navigate_task | NavigateTask Action |
| 获取阶段/位置/剩余距离 | 同一任务的Feedback | Action反馈 |
| 获取成功/失败原因和最终位置 | 同一任务的Result | Action结果 |
| 返回记录的初始位置 | 把A再次作为目标发送 | 同一个Action，非专门回家接口 |
| 可选起点核对 | check_start及start_x/y/yaw | Action目标字段 |
| 取消任务 | /navigate_task/_action/cancel_goal | 标准Action取消服务 |
| 停止锁定/解除 | /lite3/set_stop | std_srvs/SetBool服务 |
| 手动/导航模式切换 | /lite3/set_navigation_mode | std_srvs/SetBool服务 |
| 手动速度输入 | /cmd_vel | geometry_msgs/Twist话题 |
| 任务总预算 | task_timeout启动参数 | ROS参数，启动时读取 |

启动任务节点（仅等待）：

```bash
ros2 run lite3_navigation mission_manager --ros-args -p use_sim_time:=true
```

另一终端输入目标（会实际移动，目标应在当前地图可通行区域且不是已经到达的位置）：

```bash
ros2 action send_goal /navigate_task lite3_interfaces/action/NavigateTask \
  '{goal_x: 4.0, goal_y: 4.0, goal_yaw: 0.0}' --feedback
```

任务结束后返回A的示例（仅当记录的A确实是此位置）：

```bash
ros2 action send_goal /navigate_task lite3_interfaces/action/NavigateTask \
  '{goal_x: -4.0, goal_y: -4.0, goal_yaw: 0.0}' --feedback
```

取消任务、锁定停止、确认旧任务已结束后显式解锁：

```bash
ros2 service call /navigate_task/_action/cancel_goal action_msgs/srv/CancelGoal '{}'
ros2 service call /lite3/set_stop std_srvs/srv/SetBool '{data: true}'
ros2 service call /lite3/set_stop std_srvs/srv/SetBool '{data: false}'
```

这三个命令不是必须一起连续执行：取消入口负责协调停止，直接锁输入不取消任务，
显式解锁必须等旧任务清理确认后再由用户决定。取消服务返回仅表示接受请求，不是清理结束。
Ctrl+C关闭客户端/任务节点不能代替取消。

手动模式（先结束导航任务）及速度示例：

```bash
ros2 service call /lite3/set_navigation_mode std_srvs/srv/SetBool '{data: false}'
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist \
  '{linear: {x: 0.32}, angular: {z: 0.0}}' --rate 20
```

linear.x前后、linear.y侧向，单位m/s；angular.z转向，单位rad/s。实际效果取决RL。
当前已实测前进、转向和停车。停发超过约0.5秒，运动节点目标速度归零，不是瞬时停车保证。
导航模式可手动选择：data=true；新任务节点会请求导航来源，但从不解除停止锁定。

## 查看与调试

```bash
ros2 topic echo /odom --once
ros2 run tf2_ros tf2_echo map base_footprint
ros2 topic echo /joint_states --once
ros2 topic echo /clock --once
ros2 node list
ros2 topic list
ros2 action list
ros2 topic info /nav_cmd_vel --verbose
```

tf2_echo持续输出，Ctrl+C结束查看。节点/接口列表不是自定义任务状态查询，/task_status尚未实现。

## RL与Gazebo准备

```bash
cd /home/ma/Lite3_rl_deploy/build
./rl_deploy --ros-velocity
```

RL终端：z请求起身，等待至少4秒后c进入RL；ROS速度方式下空格锁定零速度，RL状态下c解除此锁。
x/X请求趴下、r请求关节阻尼属于底层调试，不是任务取消或跌倒恢复。
w/s/a/d/q/e在--ros-velocity方式禁用；默认旧键盘方式仍保留，但不经过ROS运动节点停止锁定。

已source的另一终端控制Gazebo接管：

```bash
gz topic -t /lite3/control_mode -m gz.msgs.StringMsg -p 'data: "external"'
gz topic -t /lite3/control_mode -m gz.msgs.StringMsg -p 'data: "stand"'
```

external要求新鲜有效RL关节包，stand是固定站立控制，不是任意摔倒后的自主起身。
/lite3/control_mode属于Gazebo Transport，而不是ROS2话题。
完整系统启动见RUNBOOK；新Action入口的真实Gazebo行走/取消尚待用户验收。
