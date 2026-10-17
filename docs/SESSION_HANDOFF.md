# 接续开发记录（最新更新 2026-10-17）

## 2026-10-17：按用户要求完整同步GitHub

用户在本轮明确授权把全部已完成成果、必要说明和最近bug修复过程同步到现有GitHub。
目标STAR-626/lite3_ros2_navigation，private/main，提交作者STAR-626 <hanchao.ma@outlook.com>。
保存六个包、感知/导航优化/GUI/配置/世界地图、测试脚本和证据；外部RL六份源码、补丁与策略均重新核对并重放一致。
README改为当前统一介绍，旧版原样归档；新增根CHANGELOG，按现象→诊断→修复→失败→最终测试整理。
已有ARCHITECTURE/ROADMAP原文保留；最新功能读README/终端手册/本记录，旧检查点按日期阅读。
完整文件树/清单和SHA256见PROJECT_TREE、PROJECT_FILES、SNAPSHOT_MANIFEST；检查范围/排除和许可见SYNC_AUDIT。
本轮只做同步整理与静态/恢复检查，没有再次运行机器人，也不把原有测试称为全新电脑验收。
推送是否成功和最终commit以Git历史及GitHub main为准，清单不循环记录本次commit自身hash。


## 2026-10-17：完整轮廓、换路偏好及显示优化（当前最终安装）

用户针对“中心线有路但身体过不去、卡住后不换路”授权优化，已退出系统并自行安装Smac1.3.13。
默认planner改原生SmacPlannerLattice、5cm diff运动集，launch用实际share路径覆盖空占位。
目标tolerance=0，矩形仍.84×.40m、20cm内切半径、膨胀.6；全局更新5Hz。
planner_navfn.yaml保留原配置，planner:=navfn对比回退。
默认MPPI vx_min=-.30、vx_max=.40并优先前进，Lattice允许反向扩展；controller:=rpp时launch关闭反向扩展。
近目标RPP NoValidControl时回到原生MPPI机动，goal_approach_retry=2实际秒后再试RPP，碰撞检查从未关闭。

现有global_costmap新增RoutePenaltyLayer（不加节点）：接收mission_manager失败路线Path，
代价200/.18m/12实际秒，保留真实障碍/未知，任务结束清空；是偏好，不是虚构障碍。
mission_manager新增执行路径/lite3/navigation_path、任务文字/lite3/navigation_marker，
恢复/结束清除路径；RViz原/plan仅保留默认关闭的规划预览，避免旧线误导。
get_navigation_state新增last_result_code/message，IDLE仍可看最后结果。
初始Nav2目标206→任务INVALID_GOAL3、起点205→BLOCKED2；恢复中仍等待/有限重试。
原用户取消、停止优先、3秒无进展/首次.5等待/最多5次恢复规则保留，不改RL和原整体架构。

本轮实际验证（不能混作旧版本结果）：
- 域200任务协议/显示/结果分类15项，域206真实RoutePenaltyLayer4项通过。
- 域204真实NavFn/Lattice：50cm直角通道旧算法156点，新算法208无路；开阔图可规划，
  软代价使路线改变约.213m；原用户快照目标完整轮廓受阻，新算法206。
- 域197+GZ_PARTITION=lite3_avoidance_validation_20261017：最终仓库(-4,-4)到(4,3.5,0)SUCCESS、重规划0，
  最终(3.999498,3.436021)、yaw约.19364；日志实际出现终点RPP拒绝→MPPI机动→到达。
- 最终移动箱子途中投放/持续.18m/s横穿，主任务SUCCESS、重规划5，追加90°目标也成功；
  接触数据有心跳，机器狗-箱子接触0。并非所有动态场景保证，5次恢复已接近次数上限。
- 中间失败全部归档：旧(4,4,0)雷达图目标轮廓触边；仅前进限制下移动箱子BLOCKED；
  后退启用后终点RPP卡住。分别修正目标明确拒绝、匹配后退动作、RPP受阻交还MPPI后复测。

源码和默认install已构建；新用户终端需要source后启动。未在默认用户域发运动任务，未提交/推送Git。
证据含完整原始结果/失败/本轮诊断图，见docs/development_history/evidence/footprint_replanning_2026-10-17/README.md。
详细说明docs/FOOTPRINT_REPLANNING.md；操作与新接口docs/TERMINAL_COMMANDS.md顶部。
整仓git diff --check发现原有URDF CRLF行尾被判空白；本轮navigation/perception/文档范围检查通过，未无关重写URDF。
下一步请用户现场验收原受阻场景；不要继续缩小轮廓或关闭碰撞检查来强行通过。
仍无SLAM、崎岖地面剔除、跌倒恢复、多物体/任意动态场景保证。


## 2026-10-17：用户要求缩短停车等待，已更新并复测

此节更新下方第一版的旧时间值：stuck_timeout从8改3实际秒；replan_wait从2改.5实际秒，
新增replan_wait_max=2，同一受阻窗口连续无路按.5→1→2→2退避；新受阻窗口重置首等。
新增progress_angle=.20rad，有效平移10cm或转向.20rad任一刷新进展，避免3秒误杀正常原地转向。
MPPI failure_tolerance从1.5改.5仿真秒。最多5次/恢复25秒/任务120秒/取消停止优先均保持。
不修改RL、.4/.6速度上限、20cm轮廓或整体架构。参数是启动时读取，不能只param set就假定运行逻辑改变。

用户本轮再次确认退出bringup后构建导航包。独立200域12项恢复协议通过（旧10+转向跨pi进展/时序退避）；
独立197域真实移动箱子+追加90度导航通过，结果0、retry3、728条非空接触消息，机器狗与箱子接触0。
WAITING_OBSTACLE→REPLANNING日志间隔约.50/.55/.55仿真秒；不等于“看到任何箱子后.5秒必绕过”。
未比较相同随机轨迹的总到达时间，不宣称整程必然更快。证据
`docs/development_history/evidence/faster_replanning_2026-10-17/`保存完整结果/哈希/边界。
源码/默认install已更新；实际测试退出，UDP端口全部释放；未提交或推送Git。
用户重启正常bringup、等READY、开启总开关即可继续选点/终端导航。手册与CONTINUOUS_AVOIDANCE已同步。
下方“82项/8秒/2秒”等为第一版历史验证，不是本轮当前默认值或新验收总数。


## 2026-10-17：持续避让第一版已构建安装并完成有限实际验收

用户授权实施持续移动物体避让，确认退出旧bringup，并自行安装MPPI（Jazzy1.3.13）。
此次没有修改RL源码/权重，没有新增常驻ROS节点，没有改原ARCHITECTURE/ROADMAP，未提交/推送Git。
实际系统测试只在ROS域197、GZ_PARTITION=lite3_avoidance_validation_20261017；各次顺序执行。

### 当前实际实现

- 默认controller=mppi。FollowPath插件是本包AvoidanceController：途中调用原生MPPI，
  距最终目标0.65m内切原生RPP短接近/原地转向，0.80m退出防反复切换。两者同一controller_server/costmap，
  原生碰撞检查保持；没有额外速度发布节点。RPP GoalApproach速度0.32、转向0.6、角加速度12；
  max_robot_pose_search_dist=1000使晚接管时能在完整长路径中找到实际位置（此前默认2m导致长路线103）。
- MPPI配置controller_mppi.yaml独立，vx_max=.4、wz_max=.6、vy=0、DiffDrive；60×.05=3s预测，1500候选，
  ax_max=8/az_max=12；不在输出端硬抬高速度。VelocityDeadbandCritic最终关闭，避免持续逼迫前进。
  goal_checker.stateful=false且xy/yaw=.20m/rad；任务层仍.25，必须同时达标，没有放宽成功标准。
  原controller.yaml RPP整套配置仍可用controller:=rpp enable_replanning:=false回退。
- 原感知节点增加motion_forecast.py紧凑物体短期近邻关联/匀速拟合：odom中8cm网格，至少6帧/0.5仿真秒，
  最近9帧、速度.08～.8、残差≤.035；双边界位移一致、尺寸变化≤.081m抑制静止物体视角误检。
  默认未来2.5仿真秒、.25s取样、观测包围盒额外.10m；不是物体识别/完整多目标跟踪。
  /lite3/perception/forecast新增PointCloud2(odom/原仿真戳/BEST_EFFORT/depth1)，不是实测回波。
  原障碍/清除/地面/scan语义不变。status JSON增加moving_clusters/forecast_points。
- ForecastLayer独立叠加在全局及MPPI局部图的voxel后/inflation前，每轮清除旧预测再标记；空帧、
  .5仿真秒或1实际秒超时移除预测；保留静态图/实测体素，不拿预测做射线清除。真实传感器断流仍由voxel新鲜度阻挡。
  感知配置flat_ground.yaml的forecast_enabled/horizon/padding需构建重启；仅平地。
- mission_manager内部RECOVERY_STOPPING→WAITING_OBSTACLE→REPLANNING→RECOVERY_RESUMING→FOLLOWING。
  默认104/105/106或8实际秒无10cm位置进展触发，等待2秒、全任务最多5次重规划；单次受阻窗口25秒、
  规划8秒、任务120秒。初始无路1，有限恢复耗尽BLOCKED=2；不是物理接触/跌倒分类。
  反馈replan_count/结果retry_count真实累计，重规划仍从实际位置到原目标。
- motion新增/lite3/set_navigation_pause SetBool，仅暂停导航来源并清零，不更改用户stop_locked。
  自动恢复不调用set_stop(false)；用户取消/总开关false/系统故障优先。迟到响应清理后才释放busy。
- moving_obstacle CLI及40cm实体动态箱子，Gazebo独立/lite3/dynamic_box/cmd_vel（不是ROS机器人速度）。
  工具查询实际scene拒绝已有同名实体；有限实际时间运动，Ctrl+C/结束发零速，--remove可移除。
  create/remove的Boolean只是请求入队，不能当作实体唯一/已消失证明，测试已据此检查实际scene。
  自定义BoxContacts只请求物理碰撞ContactSensorData并在发布间隔累积接触对，20Hz含空帧，纯验收不改变力。
  默认world不自动加入箱子；箱子真值只供测试，导航不订阅。正常world几何未因本功能改变。

### 已实际通过及证据

完整证据目录：docs/development_history/evidence/continuous_avoidance_2026-10-17/。
README/summary.json/manifest.json说明每项范围、来源/哈希；*.json.gz是完整结果无损压缩。
trajectories.png展示实际轨迹。没有用“消息收到/规划出线”代替真实行走验收。

1. 真实Gazebo/RL空地响应采样；0.2m/s可慢走、0.2rad/s转向弱，0.6rad/s平均约.55；
   0.6m/s后1.5秒零速仍移约.097m，不能称为普遍阈值/最坏制动界限。rl_response.json。
2. 移动箱子：机器人前进.35m后投放40cm箱子，以.18m/s横穿；雷达/预测/两图/NavFn/MPPI/RPP/RL真实闭环。
   任务SUCCESS、重规划3次、非空接触消息681、机器狗-箱子接触0；追加目标(-.5,-2,90°)也成功，接触检查覆盖全过程。
   moving_with_turn.json.gz（/tmp/lite3-avoidance-moving-kdh9ix5a/result.json）。
3. 途中新增静止箱子：SUCCESS、重规划0、非空接触消息228、机器狗-箱子接触0。
   static_box.json.gz（/tmp/lite3-avoidance-static-d2iatxpv/result.json）。
4. 最终配置原仓库到(4,4,0)SUCCESS、重规划0，最终(3.99055,3.91422)、yaw约.196rad。
   warehouse.json.gz（/tmp/lite3-avoidance-clear-kraggnjs/result.json）；没有记录全部货架接触，不能宣称全仓库零接触。
5. 真实任务旧协议16项/总开关15项/新恢复10项，域198/199/200；真实运动节点+UDP24项域201。
   均不代表实际被围死Gazebo验收。感知几何/运动估计单元9项；真实Nav2 ForecastLayer TF/清除/过期/静态图保留4项域202；
   无机器狗Gazebo工具有限停车/同名拒绝/Ctrl+C/移除4项域203。总82项模块/协议检查。

### 失败与实际限制必须保留

早期纯反应式MPPI虽绕行仍与移动箱子擦碰，因此增加短期雷达运动估计；不能把早期到达算无碰撞。
后续发现目标附近漂出容差、纯MPPI转圈、长路线RPP晚接管103，均保存失败JSON并修正后复测。
它们不应被解释为已解决所有动态避障。当前是有限单物体、平地、低速横穿第一版；
快速迎面/突然转向/多目标合并遮挡/视角假运动/真实被围死/仓库动态物体组合还需逐步验收。
20cm用户指定内切半径、完整轮廓.84×.40m继续保留，站姿宽约.375m，不能保证完整步态外摆。
没有SLAM/崎岖地面分割/跌倒恢复/重新训练。原固定地图+仿真真值定位方案保留。

### 操作与接续

四包已构建安装；source后正常bringup，不自动发目标，总开关仍默认false。
默认用户域没有发送运动任务。测试全部退出，实际UDP端口20001/30010/30011已释放（最终交付前再次检查）。
日常两终端命令、移动箱子位置/速度/时间单位、停止/退出及参数见docs/TERMINAL_COMMANDS.md；
具体实现与边界见docs/CONTINUOUS_AVOIDANCE.md。后续更改接口必须同步手册。
下一步先由用户可见验收已知目标/新箱子/移动箱子，再扩展仓库动态场景和速度/遮挡边界；整体SLAM规划不变。


## 2026-10-17：持续避让实施中的历史检查点（被上方最终记录更新）

用户明确要求持续避让移动物体，已授权执行，并确认退出bringup。
MPPI安装需sudo密码，助手sudo -n失败后用户自行安装完成，版本Jazzy1.3.13。
未修改原RL/模型策略。用户系统保持退出，测试只用独立ROS域和专用GZ分区。

已编码/构建：motion新增set_navigation_pause（仅导航来源暂停，不解除set_stop用户锁）；
MM默认enable_replanning=true，104/105/106或8秒无10cm位置进展→暂停/取消旧FollowPath→
等待2秒→实际位置重规划原目标→解除内部暂停→FollowPath；全任务最多5次重规划，
恢复窗口25秒、任务120秒、规划8秒，初始无路1、恢复耗尽2、用户取消/关闭优先。
反馈/结果记录真实次数。内部恢复不调用set_stop(false)，迟到暂停响应清理后才释放busy。
mission.yaml新配置；MPPI单独controller_mppi.yaml，RPP原文件保留。
bringup默认mppi/恢复true，支持controller:=rpp enable_replanning:=false回退。
world/map_yaml绝对路径参数用于配套隔离场景，simulation桥接仍要求world名large_warehouse。

已通过：独立198域旧任务16项、199域总开关15项、200域新恢复10项，201域实际运动/UDP
24项（含暂停不能解除用户停止、仅导航暂停、清除缓存等；准确数量见JSON）。
证据临时目录：/tmp/lite3-mission-action-2jyf234l、/tmp/lite3-navigation-gate-7otcu7yl、
/tmp/lite3-replanning-u2j9z89e、/tmp/lite3-motion-modes-2mfqs6tf。

独立197域、GZ_PARTITION=lite3_avoidance_validation_20261017，真实Gazebo/RL空地校准通过，
日志/tmp/lite3-rl-response-rnd0mo53/result.json。0.2m/s空地可慢走，原地0.2rad/s响应弱，
0.6rad/s约0.55rad/s平均，0.6m/s后1.5秒零速仍移约0.097m；不是普遍阈值。
MPPI初始ax_max=2导致反复输出约0.1~0.15m/s而不走，已改候选ax_max=8/az_max=12和
vx低速惩罚weight12，未在输出端硬放大速度。真实空地3.5m目标成功、retry0，
/tmp/lite3-avoidance-clear-i0zclzyq/result.json。

新增worlds/lite3_dynamic_box.sdf带VelocityControl/PosePublisher/接触传感器，40cm立方体，
独立Gazebo话题/lite3/dynamic_box/cmd_vel。主world添加Contact系统，不改几何。
moving_obstacle.py新CLI尚待最终构建安装/验收。两次途中加入0.18m/s横穿箱子后，真实MPPI
已偏离原直线并到达，但接触传感器无消息，因此测试脚本严格判为未通过，不能宣称无接触。
失败记录/tmp/lite3-avoidance-moving-6w6euakz、/tmp/lite3-avoidance-moving-22p82uay。
首个测试桥接命名冲突及FastDDS首次服务发现已在工具中修正（辅助bridge改名+2秒发现等待）。
Contact源码调查发现读取contact/topic，已加嵌套topic但仍无数据；当前正在独立仅箱子+地面
分区lite3_contact_probe_20261017排查（exec session78106），不占用机器人UDP。
check_continuous_avoidance.py新加入costmap_at_box判定和--turn追加90度任务，尚未跑到turn。
接下来必须修复接触记录，再验证moving/static/turn和仓库，保存实际证据及完成文档。
README/AGENTS/终端手册/CONTINUOUS_AVOIDANCE已更新；source/install最终一致和退出端口待收尾。
未提交/推送Git，原用户成果和整体架构保留。禁止把工作中测试记录当作已全部完成。

## 2026-10-17：用户进一步指定20cm青圈

用户先要求减半，助手解释15cm比实际站立半宽还小后，用户指定20cm。
两图footprint横向顶点从±.28改为±.18，padding保持.02；实际检查x±.42/y±.20，
内切半径.20，前后长度/外围inflation .6/速度/碰撞开关/RL/感知均不改。
按仿真调试值使用：站立碰撞投影宽约.375m，总检查宽.40m仅多约.025m，
没有完整步态外摆覆盖保证，实走/窄通道待验收。NavFn完整朝向局限继续保留。
check_navigation_footprint.py增加50cm通道新旧矩形对照及38cm过窄检查，
与旧圆/前方箱子/横向朝向一起共6项，独立域196真实Nav2均通过。
新矩形50cm通道发布正速度后被测试主动取消；其余碰撞案例无正速度并104。
不是Gazebo实际行走。证据development_history/evidence/navigation_footprint_2026-10-17/result_20cm.json。
导航包已构建安装、源/安装配置一致，文档bash语法/Python/JSON/格式通过；测试进程全部退出。
未更改默认域运行参数、未发送实际任务/速度；用户关闭总开关并重启bringup后生效。
README/AGENTS/手册10.1同步最新值；较早30cm段落及其证据为历史，不再是默认配置。

## 2026-10-17：用户授权缩小青色区，改全局/局部矩形导航轮廓

用户截图报告明明可通行却停车。只读日志确认RPP detected collision ahead，
0.3秒patience后104；实际参数两图radius=.4、padding=.01、inflation=.6/scaling3。
不能据此断言唯一根因是轮廓，前瞻轨迹/切弯和新增障碍也可能相关。
当前站姿通过实际TF和URDF全部primitive碰撞体支持函数计算：base_footprint下
x[-.343516,.250140]、y[-.187612,.187476]，尺寸约.594×.375m；不是完整步态包络。

用户明确要求把青色区域改小。两份config替换robot_radius为同一矩形footprint：
[[.40,.28],[-.40,.28],[-.40,-.28],[.40,-.28]]，padding=.02。
实际外沿x±.42/y±.30，内切半径.30；保留前后和腿部余量，仍需实走验收。
不改inflation=.6、scaling3、速度、0.3秒等待、碰撞开关、RL或感知。
NavFn仍只做网格代价规划，不是完整矩形朝向规划；RPP完整轮廓拦截保留，
不保证所有狭窄转弯可走，也未增加任务自动重规划。

新增test/check_navigation_footprint.py，独立ROS域196、真实controller_server/RPP/StaticLayer/
InflationLayer、合成静态地图和固定TF/odom；没有Gazebo/RL/运动节点/UDP。
4项实际检查通过：.70m直通道旧圆无正速度并104，新矩形有正速度（随后主动取消）；
前方箱子仍104、横向朝向无法容纳长边时仍104。不是机器人真实穿过通道。
证据见development_history/evidence/navigation_footprint_2026-10-17/result.json。
colcon build --packages-select lite3_navigation通过，两份config已安装；运行中旧配置
不热改，用户须关闭总开关→退出bringup→重新启动，手册10.1写明核对和退出。
没有发送默认域任务、速度或改其参数；未重启/终止用户系统，未提交/推送Git。

## 2026-10-17：准备用户手动新障碍验收，未自动投放或发目标

后续用户报告箱子已出现。只读检查实际odom约(-1.232,-2.407)、yaw=-.254rad，
导航开关false、IDLE；全局costmap箱子中心99（ROS OccupancyGrid代价映射）。
请求ComputePathToPose只做预览，到(-3.25,1.79)状态4/error0，193点、5.103米，
路径距箱子中心最近约.946米；未调用FollowPath或移动/开关服务。
已在终端手册9.3补开启总开关→navigate -3.25 1.79 90及停止命令；待用户实际行走验收。
无无箱子对照，不能把此预览当作路线因箱子改变的证据，也不是中途自动重规划。

用户询问下一步。只读检查完整bringup正在运行，任务IDLE、busy=false、fault=false，
总开关true；机器狗约(-3.255,1.787)，yaw=.184rad。
新增独立手动模型src/lite3_gazebo/worlds/lidar_test_box.sdf：lite3_demo_box，
固定位置(-2.25,1.79,.205)，尺寸.3×.3×.4，static、有visual/collision。
不include到原world，不自动加载，不改PGM；添加命令直接用src绝对路径无需build。
终端手册9.3同步关闭总开关→手动添加→看雷达/costmap→指定模型移除的命令与含义。
本轮未调用Gazebo写服务或运动/任务接口，尚待用户确认可见新增/移除效果和新路线行走。
原104案例注明历史无雷达阶段，修正“当前未接雷达”的过时措辞。
任务仍一次规划后FollowPath，没有自动重规划。本轮不提交/推送Git。

## 2026-10-14：三维雷达、平地过滤、二维障碍costmap已实测标记和清除

用户明确授权三维扫描→平地版地面剔除→二维障碍投影。新增lite3_perception包和
lite3_pointcloud_obstacles一个ROS节点，随simulation/bringup自动启动。原五个包、
任务Action/总开关、RL与速度控制保持；controller_server参数与修改前YAML对比一致。
原始GPU点云720×31层、垂直-60°～+30°、10Hz仿真时间、0.12～12米，
同一bridge发布/lite3/lidar/points(PointCloud2,lidar_link,BEST_EFFORT)。
雷达TORSO前移0.30米，上方0.15米，传感器/TF一致；只增视觉不加质量/碰撞。
原安装低箱子无回波，确认下扫机身遮挡后前移；遮挡/盲区仍存在，不承诺全覆盖。

新节点查扫描同戳odom/TORSO/base_footprint TF，非阻塞重试，过期0.3秒丢弃，
按odom平地z=0.005、容差0.02筛选障碍(0.025,0.65]；TORSO包围盒自身掩蔽。
0.65为正常站姿包含雷达的固定保守上限，不是动态最高点计算。
obstacles用于标记，clearing保留真实地面/高处回波端点用于清除，ground用于显示。
/scan现在由感知节点发布，是base_footprint的720方向二维障碍投影，不能再视为
原lidar_link的单层物理LaserScan；SLAM使用需要以后单独验证，不直接承诺可用。

全局/局部costmap保留static和inflation，加入三维体素层。
原生VoxelLayer移除低箱子时会保留底部残影，补充FlatGroundVoxelLayer继承插件：
仅对地面回波在深拷贝观察中补偿基类2*resolution端点退让，使最终射线回到实测
地面附近；普通障碍保留基类保守行为，不清理地面后方/遮挡区，不改原ROS点云。
已安装Nav2 costmap 1.3.13；换版本需复核基类算法并重跑集成验证。
网格origin_z=0、z_resolution=.05、z_voxels=14；sensor_frame显式lidar_link，
不拿地面虚拟/scan原点射线清除。两观察源expected_update_rate=.5秒。
完整启动等新鲜感知才就绪；处理节点退出关闭仿真。RViz提供投影、3D障碍、
绿色Ground Points和全局/局部costmap显示，站立/运动可见性用户验收仍待进行。

验证：3项几何语义检查覆盖地面/自身/低高物体/20°倾斜/投影最近距离。
真实Gazebo机器狗站立+真实Nav2在独立域193/专用GZ分区通过：每帧22320采样位置；
低箱子(尺寸.2×.3×.15m)加入后两costmap区域0→100，持续存在不被误清除；
移除后两图恢复0。高箱子下沿0.75m高于上限，两个区域仍0。
过滤输出满足地面容差/障碍高度，投影frame=base_footprint。没有RL/FollowPath/
导航速度任务。证据docs/development_history/evidence/lidar_3d_2026-10-14/result.json，
复测src/lite3_perception/test/check_costmap_scene.py只能独立域192/193/194且专用分区。
曾有重复域测试服务发现及残留进程，核对专用域/分区后仅回收自己的旧测试进程。
用户中途重新启动默认bringup20918；立即退出助手冲突测试，改无UDP固定传感器场景。
用户再次明确退出后才完成真实机器狗站立验证，没有终止用户的进程或发送移动任务。
中途只读检查用户已启动的三维数据/投影同戳TF通过，10Hz、720投影方向、690有效方向。
四包构建安装已完成；终端手册/README/RUNBOOK同步，源check_scan已更新语义。
最终再次核对四包安装资源与源码、XML/YAML/Python/手册bash语法通过；
与本轮升级前保存的URDF转换SDF比较，原质量/惯量/关节及碰撞几何和位姿一致。
测试进程已退出，20001/30010/30011端口空闲；最终用户可见测试前保持退出。
需重启bringup加载最后的平地体素扩展，不是source自动热更新。

当前仅平地三维障碍感知/标记/清除，未实现SLAM/起伏地面分割/自动重规划。
RPP仍沿原路径，发现新阻挡可能停止/任务失败，不把本次标记测试称为动态绕行成功。
后续先用户RViz验收地面/障碍，再验证静态新障碍导航并补有限重规划。
本轮没有Git提交/推送，用户此前编辑/临时文档锁文件未删除。

## 2026-10-13：接入二维模拟雷达，实际扫描与场景变化验证通过

用户明确希望后续SLAM实时建图，授权本轮先接雷达。保留已知地图导航、RL、任务协议
和原整体架构；当前未接Nav2障碍层/重规划/SLAM，不把看见扫描称为自主避障完成。
Lite3_gazebo.urdf增加lidar_link固定TF/小圆柱外观，TORSO传感器偏移(0,0,0.15)，
GPU二维360°/720点/10Hz仿真时间/0.12～12米，无噪声模型，frame_id=lidar_link。
fixed link默认并入TORSO，无新增质量/惯量/碰撞；比较SDF转换前后的原惯性、关节、
碰撞几何/位姿一致。新增gazebo扩展使转换器显式输出空默认ODE接触/摩擦标签，未改系数。
gz_frame_id是Gazebo扩展，转换器可能提示不属于SDF并复制保留；实测正确输出帧名。
已有world Sensors插件直接复用；同一ros_gz_bridge单向/scan桥接、publisher BEST_EFFORT。
display.launch新增urdf_file可选参数，仿真使用spawn同一个URDF保证TF一致，独立展示
仍默认Lite3.urdf；原Lite3.urdf/Lite3_original.urdf未修改。navigation.rviz自动显示扫描。

本机无项目运行进程时，三包lite3_description/gazebo/navigation正常构建安装通过。
独立ROS_DOMAIN_ID=191、GZ_PARTITION=lite3_lidar_validation_20261013的无GUI站立仿真
实测/scan一个bridge发布者、BEST_EFFORT、每帧720、有效710回波、无NaN、仿真接收10Hz；
odom→lidar_link与扫描时刻TF可用，机身站立约z=0.327，雷达约z=0.477。
在测试世界新增可见/碰撞箱子后正前方距离从1.70434米降至0.77534米，移除恢复1.70434米。
验证的是真实Gazebo GPU扫描经ROS桥接，并未把障碍坐标直接写成扫描消息。
未启动RL、发速度或导航任务；后台测试/临时箱子已退出/清除。
证据docs/development_history/evidence/lidar_2026-10-13/result.json。
只读复测脚本src/lite3_gazebo/test/check_scan.py需已启动仿真，检查扫描与同时间戳TF，
不会添加箱子或发控制命令；操作手册第9.1节同步了验收命令。
新增脚本也在第二次独立后台仿真中实跑通过，约10.01Hz仿真接收、711有效回波、
扫描时刻TF可用；RViz YAML、手册bash语法及四份安装资源与源码一致检查通过。
保留原URDF CRLF，diff --check使用临时cr-at-eol选项通过，不更改Git配置。
第二次测试launch退出后Gazebo server子进程残留，核对独立分区/ROS域后仅向该测试
PID11941发送SIGINT回收；三个UDP控制端口已确认空闲，未改已有退出逻辑。
尚待用户可见RViz轮廓对齐及RL运动中雷达质量验收，尤其俯仰时地面误回波。
下一步先验收，再接Nav2障碍层；SLAM模式以后需替换固定map→odom与静态地图来源。
本轮未提交/推送Git。

## 2026-10-13：统一终端操作手册及后续持续维护要求

用户要求所有终端交互命令独立放在一个文档，并随后续开发同步更新。
已根据实际launch/节点/CLI/接口及本机teleop_twist_keyboard 2.4.1源码，重新整理
docs/TERMINAL_COMMANDS.md，作为统一日常操作入口；保留独立调试命令并明确不与bringup并行。
包含环境、构建/重启、两终端启动、只读状态、总开关、度数/弧度双入口、可选起点检查、
取消/停止锁定、手动/键盘、位置/TF/图查询、参数/错误、退出与速查表。
指出标准Action取消仅覆盖终端Action任务，GUI内部任务需关闭总开关；键盘工具是i/j/k/l
而非WASD，未虚构repeat_rate等本机未提供的参数；纯查询不驱动机器人。
最新状态查询仍注明需要更新节点才可用，没有把源码准备称为当前进程自动升级。
README和RUNBOOK加入入口链接，AGENTS写入持久维护要求：每次交互变更同次更新手册，
核对单位/前置条件/消息和安装状态，更新日期/记录，下一位AI同样执行。
本次只改文档，不重编译/运行项目、不发导航或速度、不提交推送Git。

## 2026-10-13补充：状态查询及实际104失败诊断

用户询问总开关是否自动关闭、如何查询，以及navigate -2.195 4.159 0报104原因。
实际当前节点12846日志：获得77点Path，FollowPath开始就连续collision ahead，约0.3秒
Controller patience exceeded，结果8/停止清理完成，总开关自动关闭。控制器failure_tolerance
为0.3、期望速度0.6（用户此前修改保留），当前记录位置约(-0.700,2.811)。
能确认是地图代价/碰撞预测阻止控制，不是x/y解析错误；未判定贴货架、切角、漂移或
几何配置是哪一种根因。仍没有雷达/动态障碍感知，不调整/关闭碰撞检查，也不自动重试移动。
用户本次实际新入口日志已有多个成功目标，例如Gazebo(3.907311,-2.883676)、412点Path、
约21.55秒Reached the goal；只是这条特定目标失败，不能称双入口整体不可用或任意目标均可达。

此前navigation_status是最近运行事件，非实际布尔查询。补充现有mission_manager的
/lite3/get_navigation_state Trigger：success为查询成功，message为JSON，包含
navigation_enabled/busy/fault_latched/switch_pending/phase。不更改开关/运动或增节点。
另补Nav2 error_msg空且code104时的中文含义，保留码8与具体controller日志入口。
本次仍隔离构建在/tmp，用户运行的节点/库未覆盖；需退出后仅构建lite3_navigation重启。
最终15项独立ROS域179模拟Nav2检查通过，证据/tmp/lite3-navigation-gate-2wxndx7q/result.json，
覆盖查询关闭/开启/行走/清理后状态不产生运动副作用，以及104空文本含义补充。
编译和diff检查通过，当前进程12456/12482/12846保留；没有实机/仿真移动测试、
参数修改或Git提交推送。

## 2026-10-13：导航总开关及双入口已编码并隔离验证，应用待用户重启构建

用户要求总开关开启后可Gazebo选点立即导航，或终端输入x/y/角度，非法输入明确返回。
已在现有mission_manager中增加/lite3/set_navigation_enabled SetBool（默认关闭），
异步确认TF/Nav2/运动服务→导航来源→显式解锁后才回复开启成功。关闭立即禁用入口，
取消本任务并确认输入停止/子任务终止；故障不虚称安全停止。普通任务不会自动解锁。
失败/取消/超时清理后关闭总开关；成功后仍可接下个目标。忙碌/故障不覆盖/排队。
GUI目标与Action目标共享同一Task（可空客户端handle），不增加常驻节点或自调用Action。
/lite3/navigation_status String输出最近状态/进度/结果；终端navigate临时客户端用三个位置
参数，默认角度为度数[-180,180]，转换Action弧度[-pi,pi]。非数字/NaN/Inf/范围错误
在客户端返回3；服务器同样检查有限数字/弧度，Nav2负责地图外/占据区检查及无路结果。
关闭时Action目标返回8+NAVIGATION_DISABLED，忙碌Action拒绝，GUI打印原因。
无需新增接口枚举；内部门控取消可能Action ABORTED+result7，标准取消仍CANCELED。

GUI选点按点击系统时间戳去重：每次点击新戳，2Hz重发保留戳，实际bridge已确认保留。
门控开启系统时间后才允许新点；关闭/忙碌时点击消费但不排队、不重放。当前点击默认
朝向0，橙色标记是最后点击位置而非当前执行目标。QML已更换文案，并放大以免裁切。
当前world/map/odom一致；header.stamp是UI命令标识，不是机器人仿真状态时间。
开启总开关是用户显式授权的解锁，未改变任务自动停止/清理规则。

原仿真PID7439、GazeboGUI7618、RL7817仍在运行，禁止覆盖已加载GUI库。
这次编译使用/tmp/lite3-nav-gate-build与/tmp/lite3-nav-gate-install，本机默认install
尚未应用新版；让用户先结束任务并退出旧launch，再正常构建gazebo/navigation后重启。
没有终止用户系统，也没发真实速度/任务、改RL/controller参数/总体规划或提交推送。
最终13项新门控协议检查域179通过（证据/tmp/lite3-navigation-gate-4t37pzuw/result.json），
包括开启尚未完成时关闭请求优先；16项原任务回归域178通过
（/tmp/lite3-mission-action-f0nxhtf2/result.json）。
回归测试中的显式开关解锁独立核对，任务生成停止请求仍全部true。
GUI实际库/QML事件测试及真实ROSbridge收到4条同点击标识PoseStamped通过；
未进行真实Gazebo鼠标+机器人行走的新版联动验收。使用/恢复见NAVIGATION_INTERACTION。
下方2026-10-12只选点文案是历史状态，不能覆盖本次进度。

## 2026-10-12：Gazebo 选点预览，暂不发送导航任务

新增 lite3_gazebo/gui/Lite3TargetPicker C++/QML GUI 插件和 config/target_picker.config，
simulation launch 设置 GZ_GUI_PLUGIN_PATH 并默认加载面板，既有桥接新增
/lite3/selected_goal（Gazebo Pose→ROS PoseStamped，map坐标）。不新增ROS节点，
不修改任务/运动节点、RL、速度配置、ARCHITECTURE或ROADMAP，也不发送Action/速度。
选择按钮→单击地面→橙色GUI标记+坐标，支持重新选择、取消和复制。
Gazebo坐标事件先于鼠标释放事件，两事件配对后排除拖动，GUI线程更新QML与状态；
拒绝NaN和高度不在[-0.02,0.15]m的点击，但还不做地图可通行性检查。
按2Hz发布当前选点，默认姿态w=1，时间戳0表示预览坐标；当前world/map/odom一致，
未来定位改变需转换坐标。标记只有GUI渲染，无碰撞/地图影响；退出删除自己的ns/id。
选点只保存在当前进程，无开始导航按钮、朝向选择或跨重启持久保存。
源码与安装已准备；用户需重启原bringup加载新面板，再实际点击地面验收。
新依赖Qt5/gz_gui_vendor本机已有；默认GUI布局沿用Gazebo Sim8并附Apache2许可，
新组件BSD3许可另存，不更改旧文件许可证。此功能未提交/推送Git。

验证记录：插件编译、真实QML加载/交互、标准场景事件过滤、坐标/复制/周期发布、
GUI标记请求与清理，以及实际ROS桥接检查见下方最新验证补充。
测试隔离，不操作用户窗口，不以事件注入代替真实3D射线选点可见性验收。
下一步在现有任务链路接入用户确认后的选点导航，不另造任务服务器。

本次实际验证：lite3_gazebo构建成功；CTest target_picker_interaction通过。
测试程序通过Gazebo插件加载器动态加载库/QML，选点按钮触发、拖动/高处/NaN拒绝、
选中后普通点击保持目标、取消保留、复制坐标、迟到订阅获取周期消息、GUI标记请求
及删除自己的标记均通过。面板QML离屏截图检查文字完整可读。
真实ros_gz_bridge在独立ROS域182/独立Gazebo分区收到4条PoseStamped，
map坐标(-2.5,3.25,0)、姿态w=1，未出现/cmd_vel或/nav_cmd_vel发布者。
测试进程已退出，未启动RL，不操作用户的Gazebo窗口。用户真实三维点击/标记显示待验收。
测试源码在src/lite3_gazebo/test；未执行整包全部lint或新路线行走测试。

## 2026-10-12：完整系统 launch 入口

用户要求减少启动终端。新增 src/lite3_navigation/launch/bringup.launch.py、scripts/bringup_runtime.py 和 rviz/navigation.rviz；已有 simulation/display launch 新增可选参数且原默认行为保留。lite3_gazebo 安装 maps，导航包安装新资源并补齐运行依赖。
完整入口自动播放 Gazebo，等待新鲜 /odom、12 关节与仿真时钟，启动阶段锁定速度，顺序配置/激活 map_server、planner_server、controller_server，用伪终端启动已有 RL 并发送原 z/c 状态切换，等待 ONNX ENTER 后请求 external。launch 捕获实际插件 Mode: external 日志确认接管，然后解除此次启动锁并启动常驻 mission_manager。未自动发送任务。
辅助 ROS 节点就绪后销毁，进程监管自己的 RL 并在退出时回收；UDP 端口占用拒绝新启动，重要子进程退出关闭本套系统。RL 源码/策略、Gazebo 插件、控制器参数、原任务/运动节点源码和 ARCHITECTURE/ROADMAP 未改。仍无雷达、临时障碍感知或重规划。
启动：source Jazzy 和工作空间后 ros2 launch lite3_navigation bringup.launch.py；另一个终端发送 /navigate_task。不与旧多终端入口并行。测试状态见文末/最新验证补充，不能把启动测试当作新路线行走验收。此次未提交或推送 Git。


### 本次实际验证（2026-10-12）

三包构建及新旧 launch 参数查询通过。在 ROS_DOMAIN_ID=180、独立 Gazebo 分区中实际启动无 GUI 完整系统：地图、规划器、控制器均 active（3）；地图224×224；12关节、map→TORSO TF、/navigate_task 服务端正常；就绪后临时 startup ROS 节点已销毁；运动/任务节点各一个，导航速度发布者一个。RL 自动 idle→standup→rl_control、ONNX ENTER，实际插件确认 external；默认零速下机器人稳定在约(-3.994,-4.000)。没有发送导航目标或非零速度，此验证不替代用户 GUI/新路线行走验收。
已发 SIGINT 结束此次 launch，自己的 RL 和节点退出，20001/30010/30011 全部释放；Gazebo 的 Ruby 包装进程由 launch 的 SIGTERM 超时回收机制结束。另验证 RL 文件缺失、UDP30011占用、同一ROS域遗留map_server均在启动组件之前拒绝，且不终止其他进程；空ROS域接受完整启动计划。
最终安装版本在加入旧ROS节点预检后再次实际自动启动成功。退出时Gazebo端口曾在包装进程返回后短暂占用，随后的进程/UDP检查确认已全部回收；不将瞬时占用误称为遗留RL进程。独立图预检使用自己的Context和SingleThreadedExecutor，不依赖默认rclpy上下文。
初次测试发现本机rclpy未提供qos_profile_clock，已改为明确的best-effort时钟QoS并构建、重新通过上述实际启动。无额外系统安装、无RL源码修改、无Git提交/推送。

## 完整保存与开发过程归档

用户决定当前阶段暂停新增功能、用于周一汇报，并要求把开始至今的成果和开发过程同步到自己的私有GitHub仓库。
递归扫描实际工作空间与外部RL有效改动后，保存当前5个ROS包、所有URDF/STL/world/map/配置/launch/策略与完整外部恢复快照。
新建docs/development_history：从本任务6段本地记录导出541条可获取的用户/助手可见文字（191/350），按Asia/Shanghai日期归档；导出截止本次同步请求，不包含系统/开发者指令、内部推理、工具原始输出或图片附件。
15个非文字附件块未导出，截图含个人聊天、账号/代理页面背景，不上传；不包含其他聊天或整个电脑数据。现存指定验证日志和result.json归档到evidence，消失的旧/tmp证据不伪造；源路径与SHA256可查。
另补时间线、PROGRESS_REPORT、TERMINAL_COMMANDS、RUNBOOK、实际ENVIRONMENT版本、完整同步清单及快照校验值。原2026-10-04审计保留为历史文件。
外部RL6个文件逐字节快照校验及在干净上游文件上的补丁重放通过，policy.onnx未改变；仓库保持PRIVATE，许可证原文保留。此保存步骤不发送运动、不重建运行中的动态库、不改变原整体设计，也不将隔离测试写成真实Gazebo新入口已验收。

## 最新接续点：常驻NavigateTask服务端已接入，实际Gazebo新入口待验收

用户授权助手完成任务入口接入。mission_manager.cpp现为同一个mission_manager节点内的异步状态机，提供/navigate_task Action服务端，Nav2客户端复用原ComputePathToPose和FollowPath。一个执行器串行处理回调，50ms实际时间定时器推进状态；没有阻塞等待线程或新增路线转发节点。

已实现：常驻等待、忙碌拒绝第二任务、终端Goal→完整Path→控制器、每秒反馈、任务结果和最新可用map位姿、可选起点位置/朝向核对、成功时最终位置/朝向检查。任务自动选择导航输入但从不解除停止锁定。task_timeout默认120秒，server_timeout/cleanup_timeout默认5秒，采用steady clock处理总超时/清理；TF年龄按ROS时间判断。取消、失败、超时请求/lite3/set_stop(true)及针对本任务的Nav2取消；必须等停止服务成功及下游结果确认结束后才释放忙碌。清理超时返回SYSTEM_ERROR并拒绝后续任务，Task保留以取消晚到的目标接受响应。

当前结果映射：SUCCESS=0、NO_PATH=1（Nav2 NO_VALID_PATH）、INVALID_GOAL=3（非有限数或目标在地图外/占据区）、START_MISMATCH=4、TIMEOUT=6、CANCELED=7、SYSTEM_ERROR=8。BLOCKED/MOTION_FAILED尚未实现；控制器105等失败暂归SYSTEM_ERROR并保留原Nav2码和原因。retry_count/replan_count均为0。取消清理失败时Action状态CANCELED、result_code=SYSTEM_ERROR，不能只看Action状态。缺少最终位姿时frame_id为空，并写明原因。

旧单次源码原样保存为src/mission_manager_once.cpp，可执行名mission_manager_once。其SHA256仍为1689b0c166f4c2fa70dd92b54a31ed723fbdbc765e71b63ad0ee48c7055b7836。两种入口择一运行，不同时控制机器人。新mission_manager启动时禁止旧goal_x/goal_y/goal_yaw参数，明确提示旧入口，避免静默忽略。正常成功后仍等待新目标；取消/失败/超时保持停止锁定，需用户确认旧任务清理完成再显式解锁。

构建两包通过。新增可复测脚本src/lite3_navigation/test/check_mission_manager.py，用独立ROS域178运行真实任务二进制和模拟Nav2/TF/SetBool服务，16项协议检查通过：连续任务、忙碌拒绝、完整Path交接、反馈/终点、起点不一致、无效数字/无路/非法目标/TF错误/空路线、跟随错误保留、规划/行走取消、延迟接受取消、总超时、过期位姿、清理故障锁定、晚到响应取消和停止服务拒绝；确认从不自动解锁。证据/tmp/lite3-mission-action-jd16n1ih/result.json。另单独验证旧入口指纹、新入口旧参数提示及两个安装可执行文件。测试进程均退出；没有启动实际Gazebo/RL或发送UDP/真实速度，不作为新Action实际行走验收。

下一步用户按src/lite3_navigation/README.md在现有Gazebo中测试新任务入口和取消流程。启动节点不自动导航，另一个终端ros2 action send_goal发送任务；取消使用/navigate_task/_action/cancel_goal的标准CancelGoal服务。Ctrl+C关闭客户端/节点不等于可靠取消；暂停前应先请求取消、检查最终清理结果。直接锁定运动服务仍不通知mission_manager取消。/stop_task、状态查询、阻挡重试/重规划、跌倒检测、地图与生命周期管理尚未实现，雷达后接，原总体规划不变。没有修改RL/Gazebo/控制参数，也没有Git提交或推送。

## 历史检查点：NavigateTask接口包建立，任务服务端尚未接入

用户理解现有单次启动参数导航已经能用后，授权助手建立原规划中的任务接口包。
新增src/lite3_interfaces/{CMakeLists.txt,package.xml,LICENSE,README.md,action/NavigateTask.action}。
Goal包含goal_x/goal_y/goal_yaw及可选起点检查；Result包含原方案0–8结果常量、result_code/message/final_pose/retry_count；Feedback包含phase/current_pose/remaining_distance/replan_count。
位置为map坐标，米/弧度；check_start默认false，禁用时忽略输入起点。任务结果编号不等于Nav2错误码或Action状态。

只构建lite3_interfaces，生成C++/Python等接口。构建、ros2 interface show，以及目标/反馈/结果的实际ROS序列化往返检查通过；默认起点检查关闭，0–8常量正确。没有启动测试节点或发送机器人任务，没有改mission_manager、RL、Gazebo插件、controller.yaml、ARCHITECTURE或ROADMAP，没有Git提交/推送。

现阶段/navigate_task服务端仍未实现，任务入口仍是运行mission_manager并传启动参数。接口字段本身不能执行取消、超时、起点检查、跌倒检测或重规划。下一步在现有mission_manager中增加该Action服务端，让节点常驻等待终端任务，复用ComputePathToPose和FollowPath，并逐步实现主动取消/停止锁定协调及结果分类。不要另加路线转发节点；原总体方案保持不变。

## 上一步验收：仓库长路线导航通过，转向参数已保存

用户2026-10-10确认包含转向和绕已知货架的仓库长路线成功。助手只读核对：目标(4,4)，规划起点约(-3.10,-4.00)，返回465个点，初始反馈剩余距离11.67m；控制器接受任务后约43.8秒打印Reached the goal!，mission_manager报告到达，FollowPath状态4（SUCCEEDED）。验收后/odom位置(3.967320,3.859500)，距目标0.144250m。只记录位置误差，不宣称精确最终朝向或瞬时停车。

成功证据：/home/ma/.ros/log/mission_manager_22366_1791623433295.log，以及/home/ma/.ros/log/controller_server_11015_1791617895929.log。此前486点/约12.3m是起点稍有不同的预览路线，不能替代本次成功任务的记录；11.67m是初始剩余路线反馈，不等于实际累计行走距离。

### 转向排查与保存的配置

原转向目标0.35rad/s、最大角加速度0.5rad/s²、控制频率20Hz，按控制器的当前角速度限幅，近似静止时首个角速度指令约0.025rad/s；长路线曾因没有位置进展报105。增加角加速度至4.0仍未通过，固定0.35转向测试只有身体侧动、没有明显踏步。固定0.6rad/s原地转向测试后，用户确认踏步转向成功。此结论不是策略最低转向阈值测量。

随后运行控制器设置rotate_to_heading_angular_vel=0.6、max_angular_accel=12.0，上述长路线通过。12.0的单位是rad/s²，20Hz下从近似静止允许约0.6rad/s的启动指令；目标转向速度仍为0.6rad/s。

用户已自行把这两项写入src/lite3_navigation/config/controller.yaml。本次授权助手保留这些值、补充用途注释、构建lite3_navigation并检查src/install配置一致；desired_linear_vel和min_approach_linear_velocity仍为0.32，曲率减速、碰撞检查、到达判定等参数保留。没有改RL策略、Gazebo插件或原整体规划，没有发送新的移动任务，也没有提交或推送Git。

### 仍未完成及下一步

mission_manager目前是单次客户端：每次读取终端参数、请求ComputePathToPose、把完整Path交给FollowPath、输出结果后退出。没有自定义/navigate_task、主动取消/停止协调、总任务超时、重规划、起点检查、地图发布和生命周期管理。关闭客户端不会自动取消控制器已接受的任务；运动节点停止锁定也不等于取消Action。

下一步沿原架构完善持续等待终端任务的mission_manager及任务Action、取消/停止、超时和结果分类，再增加路线验证。LiDAR、临时障碍检测与动态重规划仍后接；此次仅证明已知静态地图的一次长路线通过。启动新任务前查询实际位置，重复目标可能立即成功，不能作为新行走验证。下方待验证转弯/绕货架的文字是较早历史状态。

## 历史检查点：mission_manager自动规划并行走已通过短直线测试

用户自行添加lite3_navigation的rclcpp/rclcpp_action/nav2_msgs/geometry_msgs依赖、CMake可执行目标和mission_manager.cpp，确认规划客户端正常；随后明确授权助手执行路线跟随接入步骤。
助手保留原规划代码，在同一节点中新增FollowPath客户端，直接使用ComputePathToPose结果中的完整Path，不订阅/plan来转发。
目标参数仍为goal_x/goal_y/goal_yaw；起点由实际TF获取。按现有FollowPath/goal_checker/progress_checker配置发送，打印剩余距离/控制器速度和最终结果。
Action取消结果单独识别，避免把CANCELED且Nav2错误码0误打印为普通规划/跟随错误。
导航包两次构建通过，现有Gazebo/RL/Nav2进程没有重启；未改动模型、RL策略、插件、controller.yaml或原整体架构。

首次测试起点约(-4.062,-4.000)，获得32点路线，控制器持续发0.32m/s，但没有实际位移。临时检查程序12秒无进展后调用停止锁定并取消FollowPath，状态5（CANCELED），任务已结束。
用户发来的RL输出target mode 0对应WaitingForStand；此状态c无效，Gazebo固定站立不代表RL处于行走状态。
用户按z、等待至少4秒、再c，提供idle→standup→rl_control及ONNX ENTER日志。助手在停止锁定下等待确认，之后再次显式请求Gazebo external接管并复测。

成功测试目标(-3.2,-4.0)，规划得到30点路线；从(-4.002594,-3.998745)到(-3.377610,-4.039117)，位移0.626287m，目标位置误差0.181866m，符合当前0.25m容差。
mission_manager打印“控制器报告已到达目标”，进程退出0，最新FollowPath状态4（SUCCEEDED），最后导航速度为零。
任务结束最初2秒仍有0.032544m收敛位移，不声称瞬时停车；后续额外3秒采样140条里程计，位置漂移0，最大平面速度约9.28e-8m/s，确认停车稳定。
成功证据 /tmp/lite3-planned-route-m6lqf76z/{mission.log,result.json}；首次取消记录 /tmp/lite3-planned-route-6qwxm6qc/。临时监测程序没有保存为产品节点或新增项目测试文件。

现阶段mission_manager是单次客户端程序：每次ros2 run读取参数、规划、跟随、返回后退出。原设计中的/navigate_task、自定义结果码、主动取消/停止协调、总任务超时、重新规划、起点检查、地图发布和生命周期管理尚未实现。
Ctrl+C关闭客户端不会自动取消已接受的FollowPath；测试中的限时/姿态/位置监测及锁定取消属于外部临时检查程序，不能宣称已在mission_manager中实现。
已更新README实际进度、目录、架构数据流与运行说明，以及AGENTS接续提示；未提交或推送Git。
当前机器狗位于约(-3.378,-4.039)，成功后未锁定运动节点；没有正在执行的任务。RL/Nav2仍运行。不要重新发同一目标后把立即到达当作新路线验收。
下一步沿原规划分阶段验证转弯、绕货架，再完善任务入口、取消/结果等；LiDAR仍后接。

## 历史检查点：手工0.32m/s短直线FollowPath已验收通过

用户2026-10-10明确确认“可以了！完全正确！”。助手随后只读核对实际运行日志：
controller_server接收新任务后约2.3秒打印Reached the goal!，最新/follow_path/_action/status为4（SUCCEEDED）。
运动节点接受0.32m/s导航速度；机器狗从约(-3.996,-3.999)移动到(-3.387,-4.038)，位移约0.61m。
终点距请求目标(-3.2,-4)约0.19m，符合当前0.25m位置容差；任务结束后多次位置日志稳定。
这证明本次终端FollowPath→控制器→/nav_cmd_vel→运动节点→RL→Gazebo及位置反馈闭环实际走通。
路线是手工提交的五点短直线，不是规划器结果自动转交；不能称为已完成仓库绕障A→B导航。
0.20m/s失败与0.32m/s成功支持继续验证低速适配，但未测出最小运动阈值，也未确认虚拟网卡是根因。
desired_linear_vel/min_approach_linear_velocity保持0.32，用于这次短直线检查；弯道、低速接近、停车误差尚需验证。
下一步将ComputePathToPose返回的完整Path交给FollowPath，分阶段验证转弯及绕货架，
随后沿原mission_manager方案整合终端目标、任务取消和结果；雷达仍按用户要求后接。
助手本次没有发送移动指令，更新README/接续记录/AGENTS的验收状态；未提交或推送Git。

## 控制器接入与低速排查记录（历史检查点）

用户按教程添加了导航控制器/RPP运行依赖和 config/controller.yaml，并构建安装。
当前 controller_server/local_costmap 已配置启用；控制器以 Twist 输出，cmd_vel 重映射为 /nav_cmd_vel。
实际查询确认 controller_server 是发布者、lite3_motion_node 是订阅者。
用户提交了地图坐标(-4,-4)至(-3.2,-4)的五点直线 FollowPath；三次任务均报 Failed to make progress。
运动节点日志确认接受了0.20m/s导航速度，但对应位姿没有持续前进；不能称为路线跟随已通过。
RL以 --ros-velocity 运行，用户按c出现 Keyboard stop released，说明已处于RL状态。
Gazebo存在/lite3/control_mode订阅者，但用户未看到Mode: external打印；仅凭缺少打印不能断定接管失败。
发现Gazebo通道使用Mihomo虚拟网卡地址；用户尝试GZ_IP=127.0.0.1限定单次发布。
虚拟网卡是否导致通信问题尚未证实，不应作为确定根因记录。

用户指出此前观察到小速度可能无法驱动当前RL策略，并授权提高速度。
本次仅把controller.yaml的FollowPath.desired_linear_vel从0.20改为0.32m/s，
min_approach_linear_velocity从0.05改为0.32m/s，避免直线测试接近目标时再次减速。
选择0.32依据是既往平地ROS→RL→Gazebo测试曾在此速度走动，不代表已测出策略最小速度阈值。
曲率减速、碰撞检查、到达判定、超时和运动限幅均保留；这是短直线联调设置，
仓库绕行前仍需验证弯道速度、接近目标和停止行为，不能直接宣称适合复杂路线。
导航包构建、YAML解析和src/install副本一致检查通过；两项参数已通过ros2 param set更新运行控制器。
本次没有提交新的FollowPath任务或直接发送移动指令，等待用户重试并观察真实位移与结果。
未修改RL、Gazebo控制插件或整体架构，也没有Git提交/推送。

## 最新接续点：导航速度输入、模式互斥和停止锁定已实现

用户要求直接完成先前暂停的运动节点步骤。新增 std_srvs/srv/SetBool 头文件，
在同一个 lite3_motion_node 中加入 /nav_cmd_vel（geometry_msgs/msg/Twist）和两个服务：

- /lite3/set_navigation_mode：true 选择导航 /nav_cmd_vel，false 选择手动 /cmd_vel；默认手动。
- /lite3/set_stop：true 锁定停止，false 显式解锁。模式切换不会解除停止锁定。

两个速度回调共用 ReceiveVelocity，先判断锁定和来源，再校验有限数值、限幅并更新时间。
非当前来源和停止锁定期间的消息不改变目标，也不刷新超时计时。
ClearVelocity 清除已接受的目标、have_command 标志并立即发送零速度；模式切换、锁定和解锁均调用。
解锁不自动恢复缓存，但正在持续发布的当前来源可以通过新收到的消息重新控制。
输入是无时间戳的 Twist；“新消息”按回调接收定义，没有证明网络延迟消息的原始生成时间。
状态不跨进程持久化，节点重启后默认手动、未锁定、零速度。
单线程 rclcpp::spin 串行执行回调；保留 20Hz UDP、0.5秒实际时间超时、限幅、退出零速度及原 odom/TF。
现有 CMake/package.xml 的 std_srvs 依赖已补齐，未改 Gazebo 插件、RL、模型和原整体架构。

2026-10-10 lite3_control 构建通过。新增可重复的实际 ROS/UDP 检查脚本
src/lite3_control/test/check_motion_modes.py（默认独立 ROS_DOMAIN_ID=179，独占空闲30011接收端口）。
18项检查通过：启动/重启零速度与默认模式、两个来源同时发布时互斥、切换清零、停止锁定、
切模式不能解除停止、解锁不恢复缓存、新指令恢复、错误来源不延长两种模式的超时、
冻结仿真时间仍超时归零、NaN/Inf处理、导航限幅、原/odom和机身TF、正常退出零速度。
结果 /tmp/lite3-motion-modes-9b3z7eg_/result.json；所有自建测试进程已退出，端口已释放。
没有运行 RL/Gazebo 或发送实际关节动作；本测试不是路线跟随、真实停车时延或复杂地形验收。
本层服务只阻止速度输入，没有取消 FollowPath 等导航任务；未来 mission_manager 需协调任务取消和锁定。

### 上一步用户确认的场景与全局规划

用户2026-10-09按终端步骤下载原项目固定版本 c64bd49f2764b9d80941b51cff61b761d0112f87 的
large_warehouse.sdf、large_warehouse.pgm/yaml 和 MIT 许可。来源 PalashMendhe/robotics-amr-ws。
文件位于 lite3_gazebo/worlds 和 maps；没有复制其机器人/机械臂/整套导航系统。
现有 simulation.launch.py 已加载 large_warehouse，并在(-4,-4,0.365)生成 Lite3，时钟桥接名称对应。
用户确认 Gazebo 站立、RViz显示模型、二维地图与机器人位置对齐，以及 Nav2 规划绕货架到(4,4)的路线。
地图目前手动用 map_server 发布，map→odom 临时静态零变换，planner_server 手动 configure/activate。
新包 lite3_navigation 保存并安装 config/planner.yaml；目前只有配置，没有任务节点。
Nav2 controller/RPP 组件已安装，但未接入 FollowPath，也没有自主沿路线走到目标。
雷达留到已知地图导航接通之后，整体规划保持不变。

下一步配置 controller_server/local_costmap，使用 Twist 速度输出并重映射到 /nav_cmd_vel，
通过本节点导航模式接入现有 RL，再完成真实路线跟随验收。
之后把临时地图发布/启动管理和 map→odom 合入原约9节点方案，完成任务取消与结果。
未提交或推送 Git。下文“地图/导航输入尚未实现”等均为历史记录，以本节为准。

## 最新接续点：导航用/odom与机身TF已实现

用户授权继续下一步，并要求清楚解释工作。已有lite3_motion_node在位置回调中新增
PublishOdometryAndTransforms：校验输入world/TORSO名称、时间戳、13个有限数值和有效四元数；
归一化朝向，提取水平朝向yaw，将机身速度转到世界再转水平导航轴，按roll/pitch修正实际yaw变化率。
接近竖直（abs(cos(pitch))<1e-3）时不输出不可可靠的平面状态。
输出/odom的frame=odom、child=base_footprint，位置(x,y,0)、yaw、水平速度及yaw_rate，协方差默认零。
odom原点/轴本阶段与Gazebo world一致；base_footprint投影在z=0，并非动态识别地形地面。
同时间戳发布odom→base_footprint及base_footprint→TORSO，后者保留完整机身高度和倾斜，
两个TF组合精确还原原始机身位姿。TORSO以下仍只由robot_state_publisher发布。
没有重发旧位置的定时器，无新有效状态就不更新输出；定位失效/跌倒的任务处理尚未实现。

新增明确的tf2依赖。运动节点在仿真launch使用use_sim_time=true，但速度发送与超时仍为wall/steady时间。
display.launch.py增加fixed_frame默认TORSO，RViz用-f传入；simulation.launch.py传fixed_frame=odom。
单独展示默认滑块/电脑时间/TORSO继续保留。未改模型、Gazebo插件、外部RL或原整体规划。
三个包已构建安装。独立ROS域检查4组姿态/速度换算、TF组合、4类非法状态拒绝、
仿真时钟固定时速度0.5秒归零、不重复旧里程计。
独立后台Gazebo从(1.2,-0.8)、yaw=0.4生成机器人，实际RL接ROS vx=.25/wz=.15，
前进约0.7403米，朝向变化约0.7903rad后停发停车；573组真值/odom/TF匹配，四足TF可连到odom。
此结果不是精确速度跟踪或复杂地形验证。后台进程均退出，用户可见GUI未操作。
临时日志：/tmp/lite3-odom-projection-l35w9xwr、/tmp/lite3-odom-gazebo-1bk8kca3。

下一步用户启动统一仿真播放，检查/odom、tf2_echo odom TORSO与RViz Fixed Frame=odom的整体动作。
随后按M3接雷达/scan；map→odom需在地图原点确定后沿原设计由位姿整理功能维护，目前未发布。
ROS节点仍四个，Nav2/导航输入/任务管理仍未实现。整体规划保持不变，未提交或推送Git。
下文“仅打印/odom尚未实现”等均为历史阶段，以本节为准。

## 最新接续点：运动节点已订阅实际机身状态

用户确认ROS原始机身状态话题有输出，随后要求助手代改本步骤，并详细解释最近几步。
lite3_motion_node.cpp新增nav_msgs/msg/odometry.hpp、ground_truth_subscription_成员，
订阅/lite3/ground_truth/odom（深度10），回调读取pose.pose.position和twist.twist.linear，
最多每两秒打印world位置x/y/z和TORSO坐标下前后实际速度。启动日志增加订阅话题说明。
保留/cmd_vel、20Hz UDP速度发送、0.5秒输入超时及退出零速度逻辑，不新增ROS节点。
此步骤仅诊断接收，没有存储导航位置、发布/odom或机身TF，也没有按反馈调整运动。

检查时用户仿真/RL已退出，lite3_control已构建安装成功。独立后台Gazebo使用当前模型/插件、
独立GZ_PARTITION与ROS_DOMAIN_ID=178，复用现有三话题桥接，验证103条实际机身状态，
运动节点两次位置打印及ROS图中Odometry订阅者；同时收到83个零速度UDP包。
未运行RL或发布移动指令，后台进程正常退出；日志/tmp/lite3-position-subscription-6flzo9r4。
整体规划未改，不提交或推送Git。用户启动统一仿真并点击播放即可查看新增日志。
下一步待用户理解并确认后，在同一运动节点整理并发布/odom与机身TF。
下面较早“运动节点尚未接收位置”等记录以本节为准。

## 最新接续点：原始机身状态已桥接到ROS2

用户已自行应用位置发布补丁并确认Gazebo `/lite3/ground_truth/odom`有输出。
实际lite3_gazebo_interface.cpp已有PublishGroundTruth：最高50Hz，world位姿、TORSO速度，
仿真时间戳、有效数值检查、仿真时间回退时恢复发布；原有UDP控制协议不变。
用户随后明确授权代改桥接步骤。simulation.launch.py的已有桥接节点新增
`/lite3/ground_truth/odom@nav_msgs/msg/Odometry[gz.msgs.Odometry`，不增加ROS节点。
lite3_gazebo已构建安装，当前已运行的旧launch需要用户重启才会使用新参数。

独立ROS_DOMAIN_ID=178复用安装后的桥接动作，只读现有Gazebo；收到20条机身状态、
11条关节和384条时钟。验证frame_id=world、child_frame_id=TORSO、位姿/速度有限、
四元数归一化、至少20ms的仿真时间间隔和单一机身状态发布者。测试进程已正常退出，
未发送运动指令或操作GUI。临时日志/tmp/lite3-ground-truth-bridge-8d2gm6sc不属于源码成果。

下一步用户重启确认ROS话题，再修改lite3_motion_node接收原始机身状态、发布导航用/odom与机身TF。
目前运动节点仍只有速度发送逻辑，/odom及odom→base_footprint→TORSO尚未实现；
不要直接将原始world/TORSO状态当作已经完成导航TF或RViz世界位置同步。
整体ARCHITECTURE/ROADMAP、模型和RL代码未在本步骤改动，未提交/推送Git。
下面“位置反馈准备”是较早记录，其未加入插件等状态已被本节覆盖。

## 位置反馈准备（2026-10-08，最新接续点）

用户已确认上一节关节同步步骤正确，随后明确授权助手代改位置反馈准备的依赖文件，
并要求告诉其下一步怎么改。lite3_control/package.xml新增nav_msgs/tf2_ros depend，
CMakeLists.txt新增对应find_package和运动目标ament_target_dependencies。依赖已安装，XML检查通过。
本次不构建/覆盖控制动态库，也未修改实际插件或运动节点的位置逻辑；/odom和机身TF仍未实现。
准备让用户在现有Gazebo插件添加/lite3/ground_truth/odom原始机身状态：位置/姿态采用world坐标，
速度采用TORSO机身坐标，仿真时间戳，最高50Hz。随后通过现有bridge交给运动节点整理为导航odom/TF。
临时副本/tmp/lite3_ground_truth_next_step.cpp的发布示例语法编译通过；仅是教学预检，未做运行验证，
不能将下一步示例视为已加入项目。整体规划、RL协议、模型和GitHub保持原状态。

## 最新进度：真实关节状态、时钟与统一启动

用户在本对话已确认可见Gazebo的ROS速度前进、转向和停止；自行把运动节点加入统一launch，
并在Lite3_gazebo.urdf添加官方JointStatePublisher插件，最高30Hz发布Gazebo `/lite3/joint_states`。
用户确认手动桥接到同名ROS话题能收到JointState，随后明确授权助手修改本步骤所有相关文件。

现已修改display.launch.py：use_gui默认true，use_sim_time默认false，保留独立展示的滑块；
条件启动滑块，并向robot_state_publisher/RViz传入类型明确的仿真时间参数。
simulation.launch.py传入use_gui=false/use_sim_time=true，自动启动一个ros_gz_bridge：
Gazebo `/lite3/joint_states` gz.msgs.Model → ROS `/joint_states` sensor_msgs/msg/JointState；
Gazebo `/world/lite3_world/clock` gz.msgs.Clock → ROS `/clock` rosgraph_msgs/msg/Clock。
两条均为单向Gazebo→ROS。package.xml新增ros_gz_bridge运行依赖。已有运动节点保留。
未改URDF几何、控制插件、外部RL或整体ARCHITECTURE/ROADMAP。

description和gazebo两包已构建安装。独立ROS_DOMAIN_ID=178复用实际桥接和状态发布动作，
只读用户当前Gazebo，验证20条关节消息、656条时钟、120次相同时间戳关节角度/TF匹配、4个固定TF，
且/joint_states单发布者、use_sim_time=true、仿真不启动滑块，独立展示默认保留滑块。
没有发送运动指令，测试进程已正常退出。日志在/tmp/lite3-joint-sync-check-juljy6p2，仅供本机临时诊断。
未启动新的可见RViz窗口，动态视觉效果仍待用户关闭旧仿真/手动桥接后重启验收。

现为三个操作终端：1统一仿真(含运动与桥接)，2 rl_deploy --ros-velocity(z等4秒再c)，
3 external接管及发布/cancel速度。不要再单独运行运动节点或桥接，避免重复。
当前RViz Fixed Frame=TORSO，仅同步腿相对身体姿态；世界位置/朝向、odom、导航TF、雷达和Nav2尚未实现。
下一步用户验收可见RViz关节动作后，按原M3接入位置与传感器。未提交或推送Git。
下面的较早状态（四终端、尚未验证转向、未接真实关节）属于历史记录，以本节为准。

## 最新进度：ROS2 速度发送端

### 接收端与完整链路（2026-10-08，覆盖下文发送端阶段的未实现状态）

用户明确授权“在RL里监听”。新增外部 `interface/user_command/udp_velocity_interface.hpp`，
并修改main.cpp、state_machine.hpp、keyboard_interface.hpp和rl_control_state_onnx.hpp。
程序用 `./rl_deploy --ros-velocity` 启用30011接收；默认无参数保留键盘/手柄选择。
只有仿真构建支持此选项。绑定失败清晰报错退出，不自动抢占端口。
UDP读取在GetUserCommand非阻塞完成，不增加ROS节点或接收线程。输入为3个float的实际速度，
除以0.8匹配当前策略随后乘以0.8的尺度。每次策略观察读取同一个UserCommand快照。
250毫秒无有效包、坏长度或NaN/Inf时归零；控制循环中断后丢弃排队旧包等待新包。
只在RL模式且没有状态切换/停止锁定时接受移动，其他状态速度为零。
ROS方式下键盘w/s/a/d/q/e禁用；z站立，c进入RL或解除空格停止锁定，x趴下，r阻尼。
键盘输入加锁；使用有限等待，Stop能回收线程。官方策略其他已有并发访问风险未全面改写。

编译与接收接口测试通过：比例换算、限幅、断线、NaN/错误包、空格锁定/c恢复、状态请求立即归零、端口冲突明确退出；默认键盘w/空格仍工作。
独立后台ROS域178、独立GZ_PARTITION中验证实际ROS2→发送节点→RL→Gazebo：
ROS vx=0.32持续3.5秒，机器人前进约1.06米；停发后稳定停止。
再次移动并强制结束自建发送节点，接收端250ms超时归零后稳定停止。无NaN或姿态保护触发。
临时进程已退出，用户可见GUI未代操作；尚未验收转向、复杂地形或长期稳定性。

外部成果已更新到external目录：六份源码快照（含新增接收头）、恢复补丁和UPSTREAM.json。
从上游原文件应用补丁后与本机六文件逐字节一致。没有提交/推送Git。
下一步先让用户按根README的四终端方式在可见Gazebo验证，再推进原M2/M3路线。

### 发送端阶段记录

用户已经自行实现并验证 `/cmd_vel` 订阅、保存速度及0.5秒超时归零；随后明确授权助手修改发送端。
目前 `src/lite3_control/src/lite3_motion_node.cpp` 是真正的 ROS2 节点，已编译安装。
订阅Twist，每50毫秒发送本机UDP到127.0.0.1:30011；3个float共12字节，顺序vx/vy/wz，实际单位m/s、m/s、rad/s。
使用分量限制±0.8，拒绝NaN/Inf，初始及超时持续发送零速度。正常退出尽力发送零包，不替代接收端断线保护。
独立ROS_DOMAIN_ID=178的测试验证：三个分量、启动零速度、连续命令、停发0.5秒后零速度、限幅、NaN/Inf和正常退出。
测试使用临时UDP接收器，已经退出；没有启动Gazebo或RL。
该发送端阶段当时未实现RL接收代码，后续实现与完整测试以本节上面的最新记录为准。
单独发送端测试本身不能证明实际运动；现在已有另外的完整后台联调证据。
这次不修改整体架构，不自动提交或推送Git；保持用户之前新增的CMake和package依赖。
下面2026-10-04记录属于历史快照；“运动节点尚不存在”等旧状态由本节覆盖。

## 2026-10-04 保存快照

用户本次明确暂停新功能开发，先同步全部有效成果到 private GitHub。
整体方案沿用 ARCHITECTURE.md / ROADMAP.md，不能因上下文切换重新设计节点或改变项目目标。
根目录 AGENTS.md 是新 AI 的阅读入口；源码、预训练策略、外部改动和恢复步骤均保存在本仓库，不依赖旧聊天。只拿到私有仓库链接时仍需授权访问；新电脑需要安装环境并恢复指定版本的官方部署依赖。

## 用户偏好和既定方案

用户是 ROS2 初学者，需要中文、具体解释操作意义，使用绝对路径，不用波浪符号。
之前要求只读教学，之后明确授权助手代改看不懂的相关代码；可以在授权范围内编辑项目。
不要删除源码、重置历史、强推、复制整个第三方仓库或上传凭据。
不自行扩大开发范围；目前用户要求暂停，下一次明确继续后才开发新功能。

课程项目：Ubuntu 24.04、ROS2 Jazzy、Gazebo Harmonic、RViz2、DeepRobotics Lite3。
第一版 Gazebo + RViz、终端全部输入、预制地图、Gazebo 实际位姿定位；不开 SLAM/AMCL。
RL 只负责基础移动，导航负责规划与避障。演示不训练，但必须执行训练好的策略推理。
先使用现成策略，自训练流程后续补；首次演示不是最终验收。
RTX 4060 约 8GB 显存可供后续评估，截图中的 CUDA 兼容版本不等于安装了训练工具链。

约 9 节点目标：mission_manager、lite3_motion_node、ros_gz_bridge、robot_state_publisher、
planner_server、global_costmap、controller_server、local_costmap、rviz2。
约 11 节点备用方案仅在原设计的地图/启动管理合并难度影响可靠性时采用。
任务管理合并地图和启动管理，运动节点合并策略、位姿整理与模式选择。
手动 /cmd_vel、导航 /nav_cmd_vel、停止锁定互斥；不因为新增 package 或 Gazebo 插件就增加规划节点。

已知障碍的全局绕行与新增障碍的激光检测/局部绕行都属于项目避障能力。
起点默认用真实位置；可选用户起点只用于一致性检查，偏差大返回 START_MISMATCH。
初始无有效路径 NO_PATH、执行受阻重试失败 BLOCKED，其他结果沿用原架构定义。
允许轻度起伏，但必须 Gazebo 验证；台阶、危险地形、SLAM、移动障碍是后续扩展。

## 当前真实代码和运行链路

工作空间 /home/ma/lite3_ws，三个有效包：lite3_description、lite3_gazebo、lite3_control。
外部官方部署项目 /home/ma/Lite3_rl_deploy；原始模型仓库 /home/ma/deep_robotics_model。
GitHub STAR-626/lite3_ros2_navigation，private、main。
提交身份 STAR-626 / hanchao.ma@outlook.com。

统一启动 ros2 launch lite3_gazebo simulation.launch.py：
自动资源路径、插件路径、Gazebo 世界和 Spawn，同时包含 RViz 展示 launch。
world=lite3_world，model=Lite3，body=TORSO，z=0.36，初始暂停。
0.6 米生成高度曾导致落地压弯后腿、身体约倾斜 18 度；降低到 0.36 后固定站姿接近水平。
三份 URDF 和四份 STL 都必须保留。

lite3_control/src/lite3_gazebo_interface.cpp：Gazebo System 插件，不是 ROS2 节点。
12 关节顺序 FL/FR/HL/HR，每腿 HipX/HipY/Knee。
固定姿态每腿 [0,-0.65,1.30] rad，Kp=30、Kd=1，髋限24、膝限36 N·m。
读取 body WorldPose、机身坐标角速度与比力、关节位置/速度。
默认 stand；Gazebo Transport /lite3/control_mode StringMsg 的 external/stand 切换。
显式接管需新鲜有效控制包及全部 Kp>0。
错误格式、非有限数值或超过250ms没有有效控制包，回退 stand，需显式重新接管。
这不是速度输入超时保护，也不是摔倒自主恢复。

插件在本机127.0.0.1:20001收动作，发状态到127.0.0.1:30010。
动作240字节=60 float：Kp12、q目标12、Kd12、dq目标12、前馈力矩12。
状态188字节=double仿真秒时间戳 + 45 float：rpy3、比力3、机身角速度3、q12、dq12、施加力矩12。
机器人静止直立时加速度Z约+9.81；启动自由落体短暂接近0是可能的。
Gazebo与RL程序通过UDP；gz topic仅切模式，不是ROS2话题。
Gazebo不直接加载策略；rl_deploy使用ONNX Runtime读取policy.onnx。
MuJoCo和Gazebo是可替换的仿真端，不能同时占用20001端口；它们没有互相通信。

当前ROS2展示节点 rsp、joint_state_publisher_gui、rviz2；create临时节点生成后退出。
RViz仍使用滑块展示状态，与Gazebo真实关节未同步，观察运动以Gazebo为准。
自研ROS2运动节点、/cmd_vel、/odom、/scan、Nav2、任务管理尚不存在。

## 外部RL成果：已保存，避免换电脑丢失

上游 https://github.com/DeepRoboticsLab/Lite3_rl_deploy.git
版本 1c4a8f14c9c531903fa5a26783e3f9b99d1039d9。
模型子模块 b452a1f404d37155400242f18e454fed8bcc51b8。
策略 policy/ppo/policy.onnx，758441字节。
SHA256 efa6581d314d8c0442881453d39fc082c09b28bbaa3029d328fcd61fa25b57c7。
C++构建 BUILD_PLATFORM=x86 BUILD_SIM=ON SEND_REMOTE=OFF。
必须从 /home/ma/Lite3_rl_deploy/build 运行 ./rl_deploy，因为策略路径相对当前目录。

已实际修改的3文件在external/lite3_rl_deploy/snapshots完整备份并生成补丁：
- keyboard_interface.hpp：空格将前/侧/转速度归零，松开按键本身不停车。
- lite3_test_policy_runner_onnx.cpp：OnEnter清零last_action。
- rl_control_state_onnx.hpp：先policy OnEnter再启动线程。
其余源文件未改。MUJOCO_LOG.TXT的改动是生成诊断，不作为源码提交。
补丁不代表已消除官方控制器全部并发访问风险；不要擅自声称完整线程安全。

每次z等待至少4秒再c，确认rl_control后再external接管。
键盘w/s前后、a/d侧向、q/e转向、空格零速度；当前不是ROS2速度接口。
上游策略默认角度和动作缩放与本插件关节顺序已经对齐。

## 验证证据和未验证范围

用户确认模型显示、固定站立和状态打印。
独立后台Gazebo（独立GZ_PARTITION，不操作用户GUI）验证：
- 状态包长度188，有限数值。
- 显式external接管、超过250ms断线回退。
- NaN控制包拒绝并回退stand。
- 真实官方策略站立、前进、空格停车；一次x从0.00881085到2.16206米，约2.15米。
  最后roll=-1.15637°、pitch=0.281619°、height=0.343679米，没有NaN或姿态保护触发。
  有小幅方向偏移，不能称为精准路径跟踪。
单次平地测试不等于转向/台阶/起伏/长期稳定验收，也不等于导航已完成。
恢复补丁会用上游原始三文件副本做apply检查，不能误称全新电脑全流程已实测。

## 下一步保持原计划

用户明确继续时，先确认可见Gazebo的RL平地表现，再接入ROS2 /cmd_vel。
将已有运动能力纳入lite3_motion_node，速度要求交给策略，保留已验证的底层关节接口。
实现零速度停止行走及速度输入中断归零；停止平移不应直接清除全部关节力矩。
之后实际关节同步、/odom和导航TF、时钟/雷达、预制地图、Nav2、终端任务与异常结果。
遵循原手动/导航模式互斥和约9节点设计，不先跳到Nav2。

完整启动命令见根README和src/lite3_control/README，外部恢复见external目录README。
不要对运行中Gazebo正在加载的安装动态库直接覆盖；让用户正常退出旧进程后构建/重启。
