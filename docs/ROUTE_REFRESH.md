# 行走中路线优化

## 2026-10-18：后台路线优化已接入（旧箱子清除之后）

mission_manager在FOLLOWING期间每约2实际秒向同一ComputePathToPose规划器请求候选路线，
当前FollowPath继续执行。以实际当前位置比较两条路线剩余的二维几何长度，至少缩短0.5m且15%才切换；
距目标1m内不切换。候选计算超过1.5秒、起点距当前位姿超过0.6m、坐标/朝向/目标不符或规划失败，
均保留当前路线。只做明显缩短，不宣称每次更短就更安全或获取数学全局最优。
所有新路线仍由原Nav2全轮廓规划与控制器碰撞检查负责。

使用原FollowPath Action的原生抢占更新路线，不调用导航暂停或用户停止服务；
代际标识隔离旧FollowPath反馈/结束回调。取消/总开关OFF、恢复和到达清理同时取消后台规划及旧控制句柄，
晚到接受/结果不启动新运动。到达会短暂经过FINISHING，待后台子任务确认结束后才释放busy。
新路线接受超时会停止并按原规则清理。更新不刷新运动进展计时、不消耗原最多5次受阻恢复预算。
背景优化不用于替代受阻恢复；新增障碍若需要更长绕行，仍由原局部避让/暂停恢复处理。

新增mission.yaml参数：enable_route_refresh=true、route_refresh_period=2、route_refresh_timeout=1.5、
route_refresh_min_gain=.5、route_refresh_min_ratio=.15、route_refresh_goal_distance=1。
enable_replanning=false也会关闭后台优化；参数启动读取，修改后构建并重启。
/lite3/get_navigation_state新增当前任务route_updates（已接受的优化路线次数）及route_refresh_pending。
到达/取消后任务释放，route_updates归0，不是累计历史；受阻retry_count/replan_count原语义不变。
日志“路线优化：剩余 X → Y”表示发送交接；RViz /lite3/navigation_path在新控制目标接受后才更新。
planner的/plan还可能含未采用的候选，不能把它当作实际执行路线。

验证：12项后台优化/阈值/取消/晚到接受/到达协议、4项原生RotationShim+MPPI交接验证通过；
原16项受阻恢复回归通过（该套显式关闭后台优化以隔离计数，新套独立验证开启状态）。
真实Gazebo GPU雷达→感知→双costmap→原生Smac Omni→任务节点→原生MPPI链路通过：
移除测试箱后，路线几何长度约3.45m→2.33m，route_updates=1，交接期间无暂停/停止服务请求。
该链路使用静止合成里程计、独立雷达架，未加载机器狗或RL；不是完整运动实走验收。
这补齐“旧障碍清除后仍走旧绕行线”的处理，但不能宣称此前所有动态卡住问题已修复。
仍需用户仓库中放箱/移箱/返回验收；盲区、无路、接近终点、改善不足等情况下不保证切换。
原整体架构、节点数、RL与控制参数保持；未提交/推送Git。

## 现场验证

系统需要重启生效。本次已构建，不用重新安装依赖。

终端1：

```bash
source /opt/ros/jazzy/setup.bash
source /home/ma/lite3_ws/install/setup.bash
ros2 launch lite3_navigation bringup.launch.py
```

终端2：

```bash
source /opt/ros/jazzy/setup.bash
source /home/ma/lite3_ws/install/setup.bash
ros2 service call /lite3/set_navigation_enabled std_srvs/srv/SetBool '{data: true}'
```

在可观察的开阔通道放箱，等costmap标记后选一个需要明显绕行的较远目标。
机器狗开始绕行后，将箱子移到其他位置，原位置需在雷达有效视野和量程内。
观察旧障碍消失、后台规划后是否出现“路线优化”日志及执行路线改变；不要把箱子放到机器狗身上。
若已经快到目标或绕过去大半，新路径未达到双阈值时保持原线是预期行为。

任务进行中查询：

```bash
ros2 service call /lite3/get_navigation_state std_srvs/srv/Trigger '{}'
ros2 param get /mission_manager enable_route_refresh
ros2 param get /mission_manager route_refresh_period
```

route_updates>0表示本次任务已接受更短路线；任务结束后归0，历史看日志。
route_refresh_pending=true表示后台请求尚未结束，查询瞬间为false不代表功能未开启。
若旧紫色障碍未消失，仍需检查雷达清除；提高规划频率不能代替地图清除。
若出现BLOCKED、保护轮廓重叠或实际跟踪偏差，属于原避障问题，保留现场日志另行诊断。

## 隔离检查

这些脚本自行启动并清理隔离节点；不是用户日常启动命令。不要同时重复启动同一隔离域。

```bash
ROS_DOMAIN_ID=215 python3 /home/ma/lite3_ws/src/lite3_navigation/test/check_route_refresh.py
ROS_DOMAIN_ID=216 python3 /home/ma/lite3_ws/src/lite3_navigation/test/check_route_refresh_native.py
ROS_DOMAIN_ID=214 GZ_PARTITION=lite3_clearing_20261018 python3 /home/ma/lite3_ws/src/lite3_navigation/test/check_route_refresh_clearing.py
```

第三个启动无GUI Gazebo静态雷达测试世界、规划/控制/感知和模拟运动服务；不会启动RL或机器狗。
测试使用已安装的工作空间配置，修改源码后先构建。证据目录：development_history/evidence/route_refresh_2026-10-18。
