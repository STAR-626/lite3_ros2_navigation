# 障碍判定与卡住修复证据（2026-10-18）

以用户本机实际日志、实时图和位姿为依据。原整体规划、RL策略和20cm内切半径未改。
本轮代码尚未提交/推送；根SNAPSHOT_MANIFEST与SYNC_AUDIT描述2026-10-17同步，不能冒充本轮快照。

## 最终验证

|证据目录 cases/ 下|验证范围|实际结果|
|---|---|---|
|native_diff_start205 / native_omni_start_success|同一用户实时图、同一实际起点、原生NavFn/Lattice；没有机器人命令|diff 205；omni 156点路线。只能证明冻结图上的规划改进|
|rl_lateral|真实Gazebo/RL平地左右横移、斜向，各2仿真秒|左约0.375m、右0.406m、斜向0.570m；没有训练新策略|
|final_low_box_clearance|真实雷达/TF/感知/全局及局部图，没有RL任务|15cm箱子两图0→100，移除100→0；下沿75cm的高箱未标记；22320原始点|
|final_native_ground_tag|真实Nav2体素层，域207，无机器人|四项通过：低物体保留、非地面端点不清自身、ground字段补偿生效、地面不清上方体素/静态障碍|
|final_user_box_warehouse|真实Gazebo/RL，途中加入1m箱(0.6294,0.618,0.505)，目标(4,3.5,0)|SUCCESS，重规划1次，最终约(3.9964,3.4162)、yaw0.188；791条非空接触数据，测试箱与狗接触0|
|final_moving_and_turn|空地真实Gazebo/RL，途中箱子持续0.18m/s横穿，再追加90°任务|两个任务SUCCESS；主任务重规划5次；450条非空接触数据，测试箱与狗接触0|
|final_replanning_protocol|真实最终mission_manager + 模拟Nav2/TF/运动服务，域200|16项通过，新增103 INVALID_PATH恢复；用户停止/取消优先仍通过，无机器人运动|
|unit_result.json|感知几何、地面拟合、回波确认、预测历史|20项通过，无Gazebo/RL|

实走使用ROS域197和GZ_PARTITION=lite3_avoidance_validation_20261017；退出用户系统后才占用UDP。
地面场景使用域192和专用GZ分区；原生规划器域204。
最终感知/控制/规划配置实走通过；随后增加的103恢复分支在独立协议测试中验证，不能声称实走触发了该分支。
没有在用户默认域替用户下发任务；验证结束进程已回收、控制UDP端口已释放。

## 失败与中间结果也保留

- user_goal_map：当时目标中心空闲，但实时图有额外致命格；重规划206，不能直接断言这些格均对应真实障碍。
- user_start_map：实际矩形未碰致命格；原diff全部相邻动作无效，205并不等于已经物理碰撞。
- failed_plane_only_static：仅地面拟合/ground标记不足以解决问题，仍在目标206后失败。
- failed_tf_transient：一次短跑因TF位姿失效返回8，具体触发年龄未留在当次日志，不能宣称已修复其根因；现增加诊断警告。
- arrived_but_bad_surface_assertion：任务成功，但测试仅查1m箱子中心，没有查其可见表面，验收断言失败。
  修正为检查箱子表面后的intermediate_static_success通过；没有把原失败JSON改成成功。
- failed_omni_small_commands：持续输出很小的速度，实际无进展，耗尽5次恢复。
- failed_response_critic_contact：试验低速评分后，接触记录出现FR_HIP与测试箱接触，明确不通过。
- failed_response_guard_blocked：增加最终输出检查后无箱接触，但地图残留导致起点205，最终BLOCKED。
- failed_response_invalid_path103：另一试验运行偏离路线，Nav2本地路径为空103，任务8。
  **Lite3ResponseCritic已从默认列表移除且enabled=false；保留源文件/插件及experiments快照，不能默认开启。**
- failed_ground_height_assertion：一次场景检查的世界z下限断言失败；只保存原probe.log，不采用可能来自旧/tmp文件的result.json。

observation_audit是测试工具在空地对雷达回波的只读审计。只对验收比较使用Gazebo箱子位姿，
没有把真值障碍坐标写给规划器或控制器。远距地面误回波多在约1.5～3.5cm世界高度，另有箱子旧体素痕迹。
最终ground_range_uncertainty=.003是经验筛选值，不是传感器标定保证；小而细、远处低物体仍可能漏检。
竖向体素10cm×7层仅降低残留概率，未保证所有遮挡痕迹都能清除。实测障碍没有按时间盲目过期。

## 如何读取

cases中的原日志、结果、图、配置压缩为单独.gz；gzip -dc FILE.json.gz可读JSON，
Python gzip.open可读.npy；诊断png为数据重建图，不是用户RViz屏幕截图。
case_sources.json保存当次临时目录来源；diagnostic_helpers为只读排查及场景启动脚本。
SHA256SUMS只覆盖本目录文件；source_hashes.json记录交付时相关源码/配置指纹，不循环包含其自身。
接触为0只针对有传感器数据的测试箱，不证明对所有货架、全部步态或任意动态环境绝对安全。
移动场景用了5次恢复，已接近上限；低速RL响应、遮挡、快速/多目标、跌倒恢复、SLAM仍有限制。
