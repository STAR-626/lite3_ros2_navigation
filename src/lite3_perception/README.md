# 三维雷达与平地障碍处理

本包的 `lite3_pointcloud_obstacles` 是一个常驻ROS2感知节点，随simulation/bringup启动。
只处理传感器数据，不发速度、任务或停止/解锁请求；RL和mission_manager仍沿用原流程。

## 数据流程

Gazebo GPU雷达（720方向×31层，垂直-60°～+30°，10Hz仿真时间）
→ 同一ros_gz_bridge → `/lite3/lidar/points`（PointCloud2，lidar_link）
→ 扫描时刻TF补偿 → 平地/自身/高度筛选 → Nav2体素层 → 二维costmap。

雷达固定在TORSO前方0.30米、上方0.15米，传感器与TF位姿一致。
前移用于降低前方低障碍被机身遮挡的概率，不代表消除了遮挡/盲区。
无附加质量/碰撞几何，原关节和RL动力学参数保持不变。

| 输出 | 消息/坐标 | 用途 |
|---|---|---|
| /lite3/perception/obstacles | PointCloud2，lidar_link | 已过滤的障碍回波，Nav2只用于标记 |
| /lite3/perception/clearing | PointCloud2，lidar_link | 保留地面/高处的真实有效回波端点，Nav2只用于三维射线清除 |
| /lite3/perception/ground | PointCloud2，lidar_link | 地面分类调试显示，不能作为障碍标记源 |
| /lite3/perception/forecast | PointCloud2，odom | 连续雷达帧估计的未来占据，独立ForecastLayer使用，不能当作实测回波或清除源 |
| /scan | LaserScan，base_footprint | 多高度障碍的水平二维投影；不再是原单层物理扫描 |
| /lite3/perception/status | String，JSON | 分类计数/模式/高度上限/运动估计，约每2秒输出 |

所有点云/投影保留原仿真时间戳，使用BEST_EFFORT、depth=1。
处理最新帧，非阻塞等待扫描时刻的TF，过期0.3秒丢弃而不重发旧数据。
Nav2以真实lidar_link为射线原点，不拿投影scan的虚拟地面原点做清除。
无回波或被遮挡的区域不会被自动填成安全空间。

## 平地规则

配置在 `config/flat_ground.yaml`：当前concrete_floor顶面是odom z=0.005米。
先将点转换到odom，过滤地面容差0.02米；障碍候选高度为(0.025,0.65]米。
0.65米是正常站姿含雷达的固定保守上限，不是随姿态动态计算的最高点。
机器狗自身按TORSO坐标的包围盒掩蔽，近身区域也因此存在不可观察范围。
下扫地面仍保留在clearing点云，可用来清除原低障碍位置的体素。

全局/局部costmap的static_layer继续保护原地图障碍；新增voxel_layer后再inflation。
此处使用FlatGroundVoxelLayer（继承Nav2 VoxelLayer）：只对已知地面回波补偿基类
两格端点退让，基类射线实际结束在测得的地面附近，普通障碍回波沿用原保守算法。
原始点云和标记观察深拷贝隔离，不把地面后方或遮挡区域清空；仅适用当前Jazzy平地配置。
体素高度0～0.70米，0.05米/层、14层；标记高度与过滤器一致。
两种源的expected_update_rate=0.5是秒，持续断流会使costmap不再新鲜。
过滤节点退出触发整套launch关闭；启动就绪阶段等待新鲜感知输出。

仅用于平地。厘米级低障碍可能落入地面容差，有限扫描线可能漏检小物体。
起伏/斜坡需要当地地面识别与可通行判断；坑洞、跌倒恢复和全覆盖安全未实现。
2026-10-17增加紧凑物体短期运动估计，复用本节点；真实观测/清除不变。
详见[持续避让说明](../../docs/CONTINUOUS_AVOIDANCE.md)，其中记录参数、预测层失效清除及局限。
任务恢复由mission_manager负责，不由本感知节点发送速度、解锁或重新规划请求。
SLAM尚未接入；/scan是多高度近邻投影，用作SLAM前需另行验证建图/定位几何。

## 验收

日常命令见工作空间 `docs/TERMINAL_COMMANDS.md` 第9.1节。
几何语义检查：source Jazzy后执行 `python3 test/test_filter.py`。
真实场景测试 `test/check_costmap_scene.py` 必须使用ROS域192和指定独立GZ分区，
会启动测试Nav2并添加/移除测试箱子，不发送FollowPath或非零速度。
不能在用户默认演示域直接运行；场景测试必须先退出原Gazebo/RL以避免UDP争用。
