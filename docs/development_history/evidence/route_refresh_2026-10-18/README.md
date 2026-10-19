# 后台路线优化证据：2026-10-18

- protocol.json：12项真实mission_manager+模拟Nav2/服务协议，包括双阈值、旧反馈隔离、后台失败/超时、
  用户取消、接受晚到、到达及OFF清理。ROS域215。
- native_controller.json：原生RotationShim/MPPI接受新FollowPath、旧goal结果不误结束父任务、速度输出继续、取消有效。域216。
- recovery_regression.json：原16项受阻恢复，后台优化显式关闭以保持旧协议的规划计数隔离。域200。
- clearing_to_route.json：真实Gazebo GPU雷达、感知、双costmap、Smac Omni和MPPI，移箱后路线3.45m→2.33m。
  合成静止里程计/模拟运动服务，无机器狗/RL；没有证明实际运动时速度跟踪/避障全面可靠。域214/独立GZ分区。

中间测试脚手架修正：取消码用接口常量CANCELED=7；服务审计排除用户开启总开关时预期的unpause(false)；
组合传感器试验需要同一仿真时钟下的新鲜动态里程计TF，不能用stamp=0的静态base位姿冒充机器人定位。
这些是测试装置问题，未用删除碰撞检查/放宽任务成功条件使测试通过。

完整运动与用户实际仓库场景仍待现场验收。/tmp原始日志可能被系统清理，本目录保留结果摘要。
