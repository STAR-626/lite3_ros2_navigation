# 完整轮廓与受阻恢复：本轮证据（2026-10-17）

本目录只归档本轮诊断、实际测试结果和失败；不改变旧阶段证据。
`.json.gz`/`.log.gz`是无损压缩，manifest.json记录来源和未压缩SHA256。

## 最终配置真实Gazebo+RL（域197，专用GZ分区）

- warehouse_final：原仓库(-4,-4)→(4,3.5,0°)，SUCCESS，重规划0。
  最终(3.999498,3.436021)，yaw约0.19364rad。日志有RPP预测碰撞→MPPI机动→成功。
  没有记录全仓库所有接触；不得宣称全仓库零物理接触。
- moving_final：机器狗已前进后才投放实体0.4m箱子，以0.18m/s持续横穿。
  主目标(-.5,-4,0°) SUCCESS，重规划5；追加(-.5,-2,90°)也SUCCESS。
  真实接触数据正常，具体消息数和原始样本在JSON；机器狗与箱子接触计数0，检查覆盖主任务和追加转弯。
  五次恢复接近次数上限，说明边界仍脆弱，不能据此保证任意动态场景。

## 无实际机器人运动的检查

- protocol_final：域200，真实任务节点+模拟Nav2/TF/运动服务，15项。
- route_layer：域206，真实Nav2偏好层4项（软代价、移动/空/过期清除、静态障碍保留）。
- narrow_corner：域204，50cm直角通道，NavFn给156点；Lattice返回208，不给无法容纳机身转弯的路线。
- soft_preference：域204，开阔图两者都成功；新偏好使新路线偏离旧线约0.213m，代价保持非障碍。
- original_goal_rejected：旧用户快照目标的完整轮廓被挡，Lattice206（目标占用），NavFn仍给254点。

## 原问题及迭代失败必须保留

original_snapshot/plan/footprint_check和三个npy为原受阻场景。
path_footprint_check.png是采集数据的离线重建，不是直接截取RViz/Gazebo。
旧路线254个采样位姿，60处按切线矩形边缘检查碰到地图障碍格；不是60次真实碰撞。

failed_warehouse_goal：新规划器最初对旧(4,4,0)无路；实时图完整轮廓触边，改为目标tolerance0明确206。
failed_forward_only_moving：只允许前进/转向的移动箱子测试BLOCKED、接触0；匹配开启规划与MPPI后退后通过。
moving_before_final_approach_fix是后退启用、但最后接近回退尚未修正时的中间成功，不代替moving_final。
failed_final_approach：仓库几何可规划，但终点RPP重复拒绝碰撞预测，任务BLOCKED。
warehouse_final在RPP受阻交还MPPI的修正后通过。

离散轮廓/地图、RL动作误差、雷达遮挡和运动物体仍有限制；未测试任意围困、多物体、快速迎面、崎岖地形。
未实现SLAM/训练/跌倒恢复。用户现场新箱子状态需重新验收。
