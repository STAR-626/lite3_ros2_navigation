# 持续避让验证证据（2026-10-17）

当前汇总：summary.json；原始文件来源/字节哈希：manifest.json。
`.json.gz`是完整测试结果的无损gzip压缩；没有抽样或改写轨迹。可用Python gzip/json或`gzip -dc 文件`查看。
trajectories.png由三项成功验收的实际位置生成，左图含后续90度任务；箱子真值只供验收，没有输入导航。
移动箱子轨迹仅显示图中窗口内的部分，机器人轨迹完整显示。

- mission_protocol.json：旧任务16项；navigation_gate.json：总开关15项。
- replanning.json：有限恢复10项，模拟Nav2/TF，真实任务节点；未操作实际机器人。
- motion_modes.json：真实运动节点和UDP24项，无RL/Gazebo。
- rl_response.json：真实Gazebo/RL有限时长前进、转向和零速后位移采样，不是最坏制动保证。
- forecast_layer.json：真实Nav2层的TF变换、移位、空帧/过期清除、静态图保留，共4项。
- moving_box_cli.json：真实无机器狗Gazebo，限时停车/同名拒绝/Ctrl+C停车/移除，共4项。
- moving_with_turn.json.gz：真实雷达/预测/costmap/NavFn/MPPI/RPP/RL闭环，横穿箱子与追加90度任务成功，记录681条非空接触消息（主要为地面），机器人与箱子接触0；任务重规划3次。
- static_box.json.gz：行走后新增静止箱子，成功绕行，228条非空接触消息，机器人与箱子接触0；无需全局重规划。
- warehouse.json.gz：最终配置下原仓库到(4,4)成功，未使用箱子接触记录器，不作为所有货架无接触的证明。

## 保留失败记录，不能将早期到达混作成功避障

- failed_reactive_collision.json.gz：仅反应式MPPI仍与移动箱子HR_HIP擦碰；促成雷达短期预测层。
- failed_goal_drift.json.gz：避让后控制器报告成功，任务层因实际位置偏出0.25m而拒绝；没有放宽任务成功标准。
- failed_goal_orbit.json.gz：位置/朝向同时检查后，纯MPPI在目标附近绕圈；促成复用原生RPP最终接近/转向。
- failed_rpp_handoff.json.gz：长路线末端首次切至RPP，其默认2m路径搜索仍从旧起点开始导致103；修正专用GoalApproach.max_robot_pose_search_dist后仓库复测成功。

感知几何/静态轮廓变化/时钟与缺帧9项单元检查见lite3_perception/test/test_*.py。
这些是有限平地场景验证；多目标、快速迎面、突然转向、真实被围死、动态障碍仓库组合和复杂地形仍需扩展。
没有承诺任意环境零碰撞，没有实现SLAM/跌倒恢复，也未修改或重新训练原策略。

## 复测入口

先退出用户系统；真实机器人测试的UDP端口不按ROS域隔离。以下每条单独执行，实际运动测试不能并行。

```bash
source /opt/ros/jazzy/setup.bash
source /home/ma/lite3_ws/install/setup.bash
ROS_DOMAIN_ID=197 GZ_PARTITION=lite3_avoidance_validation_20261017 python3 /home/ma/lite3_ws/src/lite3_navigation/test/check_continuous_avoidance.py --scenario moving --turn
ROS_DOMAIN_ID=197 GZ_PARTITION=lite3_avoidance_validation_20261017 python3 /home/ma/lite3_ws/src/lite3_navigation/test/check_continuous_avoidance.py --scenario static
ROS_DOMAIN_ID=197 GZ_PARTITION=lite3_avoidance_validation_20261017 python3 /home/ma/lite3_ws/src/lite3_navigation/test/check_continuous_avoidance.py --scenario clear --warehouse --goal-x 4 --goal-y 4
ROS_DOMAIN_ID=202 python3 /home/ma/lite3_ws/src/lite3_perception/test/check_forecast_layer.py
ROS_DOMAIN_ID=203 GZ_PARTITION=lite3_box_cli_validation_20261017 python3 /home/ma/lite3_ws/src/lite3_navigation/test/check_moving_obstacle.py
```

真实测试的world/map临时配套生成，世界名large_warehouse。行走0.35m后才加入箱子；任何机器狗-箱子接触/跌倒立即失败并退出。
测试回收自己启动的组件，末尾检查20001/30010/30011；不会终止用户的其他仿真。
