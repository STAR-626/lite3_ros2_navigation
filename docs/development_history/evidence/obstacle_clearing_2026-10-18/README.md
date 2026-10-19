# 旧箱子记录清除：2026-10-18

before.json：旧版真实GPU雷达0.65m高箱子移除15秒后，两张costmap仍100。
after.json：新版七项真实雷达/感知/双costmap隔离检查通过；增加前景遮挡后，确认移除箱子不会盲清，
解除遮挡后约0.52实际秒旧位置清空；移动箱子旧位置清空、新位置100。
先前较简单同场景新版约0.30秒；这些是单次测量，不承诺固定时限。
ground_tag.json：四项原生地面清除/高体素保护回归。
forecast_layer.json：独立预测层回归（与本次清除语义隔离）。
sensor_layout.json：真实GPU扫描720×31组织布局。

试验用ROS域214、GZ分区lite3_clearing_20261018，只含静态雷达架/地面/测试箱，
未加载机器狗、RL或发送导航任务；没有操作用户场景，也未验证途中更优路线切换。
所有试验临时日志目录写在结果JSON中，/tmp可能被系统清理。

复现：source /opt/ros/jazzy/setup.bash 和正常工作空间install/setup.bash后，
ROS_DOMAIN_ID=214 GZ_PARTITION=lite3_clearing_20261018 python3 src/lite3_perception/test/check_removed_obstacle.py
