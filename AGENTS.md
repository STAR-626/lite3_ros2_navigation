# AI 接手入口：先读记录，再继续开发

## 2026-10-19同步检查点

近期实现与验证范围已整理进Git同步：感知回波确认/地面拟合/有效无命中清除、Omni规划控制、
安全缓冲候选、后台路线优化、Gazebo导航/动态箱子双用途面板。
当前新增箱子在全局costmap中的记录波动、由此可能反复换路：未定位、未修复；
用户要求本轮先保存，不继续改导航算法。不能把历史实走成功或固定雷达测试当作本问题已解决。
后续先做移动视角下遮挡保留与可见空闲清除验证；自然语言任务入口加入计划，尚未实现。
当前准确架构见docs/CURRENT_ARCHITECTURE.md，限制见docs/KNOWN_ISSUES.md。
本次只整理文档与已有成果，不重启或修改运行中的Gazebo/RL，不提交生成目录或凭据。

## 2026-10-18：Gazebo选点插件扩展为导航/动态箱子两用

原Lite3TargetPicker插件/加载名称保留，面板标题为“Lite3 导航与动态障碍”，分“导航目标”“动态箱子”两页。
保留原导航选点、去重时间戳、坐标复制和目标标记；放箱子不更改或发送新的导航目标。
新增箱子长宽高（默认各0.4m，范围0.1～2m）、速度（默认0.15m/s，范围0.05～0.5m/s）、
地面放置、启用WASD/鼠标方向按钮、停止、移除、检查状态。尺寸仅在创建前修改，速度可以修改。
W/S世界±X，A/D世界±Y，不随相机或箱子朝向改变；斜向速度归一化。
启用后焦点在绿色控制区，松键停车；空格/Esc停止并退出控制。切页、失焦、窗口非活动、关闭面板均停车。
点击场景调相机也会失焦停车，须再次启用控制；停止箱子不等于停止机器狗导航。

每个面板使用UUID专属箱子和Gazebo话题，仅控制/删除自己创建的一个箱子，不接管CLI或普通工具创建的物体。
创建/移除采用异步服务并查询实际scene确认，不能把Gazebo排队确认当作模型已生成/删除；
8秒无确认则锁住控制，用户通过“检查状态”核实。工作线程仅写共享回执，Qt定时器在GUI线程更新界面。
关闭面板保留停车的箱子；重新打开面板拥有新的专属箱子，旧箱子可通过Gazebo实体树删除，不自动接管。

箱子含真实碰撞/惯性、原生VelocityControl、BoxContacts及新增BoxCommandGuard（同一Gazebo库的系统组件）。
后者把世界轴命令转换成原生箱体轴命令，约300ms无新指令时输出零速度，防止GUI指令流消失后持续运动。
没有增加ROS2节点；控制使用Gazebo Transport，完全不向机器狗/cmd_vel或/nav_cmd_vel发指令。
原moving_obstacle终端工具、RL、导航架构/参数及雷达处理未修改。

构建通过，真实QML交互及独立Gazebo物理两项CTest通过：原选点过滤、尺寸、异步确认、WASD/斜向限速、
松键/空格/切页/失焦/关闭停止、真实模型位移/碰撞、90度旋转后世界轴、指令断流停车、仅移除自有模型。
测试未启动机器人或RL，未宣称整体动态避障已通过。完整系统仍保持关闭，用户需正常重启加载新版。
说明见docs/GAZEBO_DUAL_PANEL.md；证据dual_picker_2026-10-18；源码备份位于
/home/ma/lite3_ws_backups/dual_picker_20261018_224126/lite3_gazebo。未提交/推送Git。


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


## 2026-10-18：移走箱子后旧障碍清除修复

已复现并修复一种三维障碍残留：Gazebo GPU雷达用有符号Inf/零分量NaN表示量程内无命中，
旧过滤器只保留有限XYZ，丢失了这类有效射线的空闲证据。0.65m高箱子移除后，旧版全局/局部图
等待15实际秒仍为障碍100。新版本在相同场景、相同扫描位置约0.3秒清除；增加遮挡/移动验证后约0.52秒。
这些是隔离测试测量值，不是任意场景延迟保证。

仅在已知720×31、水平±pi、垂直-60°至+30°的Gazebo扫描布局中恢复匹配符号的无命中射线，
按12m量程界限生成clearing-only端点。普通全NaN、部分损坏、布局/符号不符及机身遮挡方向不补点。
不会将这些端点发布成障碍、地面、/scan或运动预测，不修改真实有限回波/时间戳/雷达原点。
仍采用原三维体素射线及普通端点退让，不清整列、不设置障碍存活超时、不清静态地图。
原地面拟合不足时整帧标记/清除暂停的规则保留。配置不适用于未经验证的真实雷达或其他扫描布局。

验证：28项感知单元检查通过；真实Gazebo GPU雷达+感知节点+全局/局部原生costmap七项隔离检查通过：
保持存在的箱子、遮挡时保留旧记录、重新可见后清除、箱子移位后旧位置清除/新位置标记、静态图保护。
旧原生地面标记四项通过。测试未加载机器狗模型、未启动RL、未发送导航任务。
不改变节点数、RL、导航控制器、规划/途中重规划策略或整体架构；当前路线不会因此自动切换为更短路线。
未保证任何姿态/盲区/扫描线间隙均可清除；箱子原位置需在量程和视野内、有有效空闲射线。
备份：/home/ma/lite3_ws_backups/clearing_20261018_214745。未提交/推送Git。

操作：重新source正常工作空间后启动原bringup；箱子移走并重新扫描后观察全局/局部costmap旧占据消退，
再发送新目标。状态JSON新增no_return_clearing计数；此计数非清除障碍数量。
回归：`ROS_DOMAIN_ID=214 GZ_PARTITION=lite3_clearing_20261018 python3 /home/ma/lite3_ws/src/lite3_perception/test/check_removed_obstacle.py`。
该工具启动独立无GUI雷达场景、两张costmap，创建/移动/删除测试箱子，最终清理自身进程；不连接默认ROS域。
证据见docs/development_history/evidence/obstacle_clearing_2026-10-18。


## 2026-10-18：停止余量与缓冲区候选修复（尚未Gazebo/RL实走验收）

用户要求自己操作，本轮由AI准备补丁、用户应用。此前用户已接入Rotation Shim并确认启动加载，
不表示长距离后退、路线偏离或全部卡住问题已解决。最近现场(-1.6755,-3.2843)、yaw约-139.4°时，
中心空闲，但当前矩形轮廓与静态地图shelf_16重叠；全局、局部、原静态图均重叠12个致命格中心。
最近三个不同目标均在规划阶段205起点受阻；重新开总开关不会恢复机器狗位置。
实际物理碰撞与地图/模型精确对应尚未证实，不能根据二维占用断言实体碰撞。

候选修改：默认AvoidanceController同时检查当前实际速度的反应+减速轨迹、新指令的过渡轨迹和
原即时响应1秒轨迹；包含平移、后退、横移、转动及机身内部小障碍检查。
靠近障碍/未知区域时限制平移速度，并对限速后的指令再次检查，不把小速度强行放大。
全局/局部及旧RPP/NavFn配置padding统一.02→.07，导航保护外沿.94×.50m，内切半径25cm。
这不是机器人真实模型变大；每侧增加5cm保护余量，20cm旧值只代表此前配置。
默认缓冲带为保护外沿向外40cm，只限速、不直接把整带设为致命障碍；RViz不会新增一条专用缓冲圈。
实际模型无改动、无新节点、保留RL/原架构，用户停止/取消及有限恢复规则保留。

参数均为启动时读取的待校准初值：reaction=.25仿真秒、linear_decel=.5m/s²、angular_decel=2rad/s²、
lookahead=1秒、slow_distance=.4m、slow_linear_speed=.32m/s（上限不是最低速度）。
例如.4m/s下模型停止距离=.4×.25+.4²/(2×.5)=.26m，所以缓冲带需宽于这一距离。
停止/跟踪误差是否被该模型覆盖必须实测；不能根据数值检查或编译宣称演示不会卡住/碰撞。
尚未实现已重叠位置的自动脱困、空闲状态躲避逼近物体、路线偏离保护或正常/脱困模式拆分。

已做：临时副本编译、14项数值回归；域209真实Nav2+合成地图/里程计的转身、实际速度制动拒绝及缓冲区限速验证。
未做：本候选配置的Gazebo/RL实走、动态箱子回归、最低可用速度及制动能力标定。
旧章节的实走结果属于此前配置，不能用于宣称本补丁已通过实走。
应用与测试见[安全缓冲操作手册](docs/SAFETY_BUFFER.md)；GitHub未提交/推送。


此仓库是用户的 ROS2 Lite3 课程项目。这个入口用于在没有旧聊天上下文时接续工作。
不要重新猜测需求或改动整体规划。用户的最新要求优先。

## 首次接手阅读顺序

1. `docs/SESSION_HANDOFF.md`：当前代码、已有验证、已知限制、用户偏好及下一步。
2. `README.md`：实际结构、环境安装、构建与三个终端的操作步骤。
3. `docs/ARCHITECTURE.md` 和 `docs/ROADMAP.md`：保留的整体设计和开发顺序。
   它们开头的“当前状态”记录于 2026-10-01，不能用来覆盖较新的进度。
4. `src/lite3_control/README.md` 和实际源码：目前 Gazebo 控制接口。
5. `external/lite3_rl_deploy/README.md`、`UPSTREAM.json`、补丁与源码快照：
   工作空间之外的 RL 项目恢复依据。
6. `THIRD_PARTY_NOTICES.md` 和 `docs/SYNC_AUDIT.md`：许可、保存范围与文件检查。
7. `docs/RUNBOOK.md`、`docs/TERMINAL_COMMANDS.md`、`docs/development_history/README.md`：完整当前启动、交互和可获取历史文字/证据。

## 固定方案，除非用户明确修改

- Ubuntu 24.04、ROS2 Jazzy、Gazebo Harmonic；Gazebo 演示，RViz 辅助观察。
- 用户通过终端操作；预先制作与 Gazebo 一致的地图，第一版使用仿真实际位姿。
- 开源 RL 负责基础移动，Nav2 负责路径规划和避障；演示执行策略推理，不现场训练。
- 精简设计约 9 个节点，原约 11 节点备用方案保留。package、进程和节点不要混为一谈。
- 手动 `/cmd_vel`、导航 `/nav_cmd_vel` 和停止锁定需要互斥。
- 轻度起伏必须实测；SLAM、危险地形理解、移动障碍和完整自训练流程属于后续。
- 最终任务结果及起点检查沿用原架构，不替换为新的任务方案。

## 2026-10-18：货架旁误报无路与额外障碍标记（当前修复）

本次以用户现场实时地图、位姿和日志为依据，不继续缩小机器人轮廓。

- 用户停在货架旁时，实际0.84×0.40米矩形没有碰到致命格，但原diff运动集中所有可扩展动作均被挡。
  原生Lattice会将这种“没有可执行下一步”的情况报成205（起点占用），不能由205反推身体已碰撞。
  同一冻结地图，原diff返回205；omni运动集可以输出156点路线。
- 默认MPPI改为Omni，允许横移，横向上限0.30m/s、采样标准差0.25m/s；Lattice同时选安装包的5cm omni运动集。
  后退、完整矩形、碰撞检查和原速度上限保留。controller:=rpp仍选diff运动集，原NavFn回退保留。
  原RL策略文件不变；真实RL左右横移及斜向移动单独测试已通过。
- 平地模式增加有界地面平面拟合，避免仅凭固定世界高度误标轻微倾斜的地面回波。
  至少80个分散地面样本、X/Y跨度各2米、坡度≤0.035、雷达脚下偏差≤2cm；不满足时丢弃整帧标记/清除，
  不推断未知区域安全。仍然只用于平地，不能据此宣称支持斜坡/台阶。
- 障碍标记增加8cm三维网格邻域至少3个回波支持、相邻两帧确认（XY邻格允许移动）。
  只过滤障碍标记，真实清除射线不因此删改；约增加一帧（10Hz时约0.1仿真秒）确认等待。
  小而细、远距离稀疏物体可能漏检，不能把此过滤当作安全保证。
- clearing PointCloud2新增FLOAT32字段ground，明确标识被判定为地面的实测端点。
  FlatGroundVoxelLayer读取此字段补偿原两格端点退让，不再依赖补偿前世界z是否恰好接近0.005。
  xyz、时间戳和真实射线原点不变；没有整列清空、按静态地图屏蔽新障碍或超时盲目删除实测障碍。
- /lite3/perception/status新增raw_obstacles（确认前计数）和ground_plane（z=a*x+b*y+c系数/null）。
  mission_manager对位姿检查失败新增时间年龄/TF查询警告，方便区分感知受阻和定位链路故障。

验证结果及保留的失败见本次证据README；原整体架构、SLAM计划及节点分工不改。
本轮修改尚未提交/推送；2026-10-17同步清单是历史快照。

后续同日补充：竖向体素10cm×7层，ground_range_uncertainty=.003，最终速度1秒完整轮廓检查。
试验Lite3ResponseCritic未通过物理回归，源码保留但默认列表移除且enabled=false；不得擅自启用。


最终本轮：仓库1m箱到(4,3.5)成功/重规划1；移动箱+90°成功/主任务重规划5；箱接触各0。
20单元、4原生体素、16任务协议及真实低箱清除通过。103路径失效现在可恢复，TF102仍非同类。
源码/install已构建；保持当前已验证配置，不默认启用试验评分器。证据见obstacle_reliability_2026-10-18。
仍有卡住限制、移动任务用了全部5次恢复，不能声称彻底解决。没有提交/推送。

## 2026-10-17：本次同步补充

用户已明确要求提交/推送现有private仓库；下方“本轮不提交推送”属于此前功能实现阶段的历史记录。
当前README为统一最新入口，旧版已原样归档。根CHANGELOG保存最近bug发现、修复、失败和复测；
PROJECT_FILES/TREE、SYNC_AUDIT及SNAPSHOT_MANIFEST保存本次扫描和校验，不改变原整体规划。

## 2026-10-17：完整轮廓与任务显示优化（最新）

用户已退出bringup并安装nav2_smac_planner。默认planner改Smac Lattice，5cm diff运动集，
目标tolerance=0，完整矩形仍.84×.40m/20cm内切半径；原NavFn保存在planner_navfn.yaml，planner:=navfn回退。
默认MPPI允许vx_min=-.30，Lattice反向扩展；controller:=rpp时launch关闭反向扩展。
任务恢复给global新增RoutePenaltyLayer软代价200/.18m/12wall秒，结束清空，不是假传感器障碍。
新增执行路径navigation_path/Marker，原/plan仅关闭的调试预览；状态JSON新增last_result_code/message。
源头检查发现(4,4,0)旧目标在一次实时雷达图部分轮廓受阻，新版拒绝不是规划器故障；可测试(4,3.5,0)。
本轮失败/修复/最终安装与测试以SESSION_HANDOFF顶部及FOOTPRINT_REPLANNING为准。
没有新增节点、不改RL/原ARCHITECTURE/ROADMAP、不提交推送。必须同步终端手册。

## 2026-10-13：二维雷达接入与后续SLAM意向

2026-10-17反应调优最新：stuck_timeout=3、replan_wait=.5、replan_wait_max=2，
连续无路指数退避，恢复运动后的新受阻窗口重置首等；progress_angle=.20rad，正常原地转向算进展。
MPPI failure_tolerance=.5仿真秒。新旧验收分开见SESSION_HANDOFF，任务最多5次/用户停止优先保持。

2026-10-17持续避让最新：用户授权实施。默认MPPI配置单独controller_mppi.yaml，
原controller.yaml保留RPP；bringup支持controller/enable_replanning及配套world/map_yaml。
任务管理增加pause→等待→有限重规划；motion增加set_navigation_pause，不能解除用户stop。
接口/参数/校准和真实Gazebo验收以SESSION_HANDOFF顶部为准，不能仅凭源码宣称全部通过。
新增moving_obstacle临时CLI和模型，不自动投放；现有感知节点增加紧凑雷达物体短期运动估计，
独立ForecastLayer逐帧清除/过期。不是完整多目标识别或SLAM，节点总体分工不改。

2026-10-17最新：用户要求青色碰撞区进一步调到20cm。两costmap矩形footprint(.80×.36m)、
padding=.02，实际外沿x±.42/y±.20，替代同日早先30cm配置。保留inflation=.6、速度/RL。
站立投影宽约.375m，总检查宽.40m侧向余量很小；不能声称覆盖完整步态。
隔离检查/构建安装实际状态以SESSION_HANDOFF最新记录为准，用户须重启生效。
实走和完整步态外沿待验收；NavFn不做完整矩形朝向检查，RPP碰撞拦截仍开。
详细依据和限制见SESSION_HANDOFF顶部、终端手册10.1；不能宣称已解决所有窄通道。

2026-10-14最新：用户授权三维雷达/平地地面筛选/二维障碍投影。
新增lite3_perception与一个处理节点；31×720点云、前移TORSO x=0.30 z=0.15，
floor z=0.005/tolerance=0.02/障碍(0.025,0.65]；同戳TF补偿，自己掩蔽。
/scan变为base_footprint二维障碍投影；raw为/lite3/lidar/points。
global/local costmap增加VoxelLayer，障碍标记源和保留地面的清除射线源分开，
真实lidar_link射线原点；静态层/膨胀层保留，不用投影scan清除。
启动等待感知新鲜，处理节点退出关闭系统。最新验证/安装状态以SESSION_HANDOFF顶部为准。
仅平地；未实现SLAM、起伏分割或任务自动重规划。新接手者必须先看/scan的语义变化。

用户已明确希望后续实时SLAM建图，本次授权先接雷达；保留原架构和先前已知地图入口。
Lite3_gazebo.urdf增加TORSO上方0.15米二维GPU雷达，/scan、lidar_link、720点、360°、
10Hz仿真时间、0.12～12米；无附加惯性/碰撞，不修改RL或控制参数。
仿真display传入实际生成的URDF，standalone默认Lite3.urdf不变；复用bridge BEST_EFFORT
发布LaserScan；navigation.rviz显示扫描。三包默认build/install已更新，测试时无用户运行进程。
独立域191/GZ分区后台站立仿真验证真实扫描、同时间戳TF、箱子添加/移除的测距变化，
未启动RL/导航任务，测试已退出。雷达运动中质量/用户可见RViz待验收。
Nav2仍静态层+膨胀层，未接障碍层/重规划/SLAM；下一步先让用户检查扫描对齐。
操作手册第9.1节、check_scan.py和SESSION_HANDOFF保存实际验收/限制。

## 2026-10-13：总开关和双导航入口

同日最新补充：/lite3/get_navigation_state Trigger只读查询JSON状态（success表示查询成功），
及Nav2 104空错误文本的中文补充已编码，隔离15项检查通过，默认install待退出后构建。
实际用户目标(-2.195,4.159,0)已规划77点，控制器预测碰撞并在0.3秒后104，
失败后关闭总开关并锁定停止；未判定具体碰撞几何根因，未修改速度/碰撞配置。

用户要求已实现于源码：现有mission_manager增加默认关闭的导航总开关，开启后
Gazebo新选点或终端navigate X Y角度共用任务状态机；CLI默认度数，Action仍弧度。
显式开启才确认系统并解锁，关闭协调取消停止，失败清理后需重开。无新增常驻节点。
GUI点击系统时间标识去重和防旧点重放，普通消息重发不执行第二次。
13项新协议、16项回归、真实GUI插件和bridge验证通过，未做真实新版行走。
为保护运行中的GUI库只在/tmp隔离构建，默认install仍旧版，待用户退出后构建应用。
详细状态见SESSION_HANDOFF顶部，命令见NAVIGATION_INTERACTION。RL/控制参数/整体规划未改。

## 2026-10-12：新增 Gazebo 选点预览

用户接受GUI选点入口。lite3_gazebo已新增Lite3TargetPicker GUI插件，simulation默认
加载项目GUI配置；当前只选位置、显示标记/坐标、复制，并通过现有bridge发布
/lite3/selected_goal PoseStamped。没有开始导航按钮，不发Action/速度、不加ROS节点。
当前world/map/odom一致；高度过滤不是地图可通行性检查。真实3D点击需用户重启验收。
详见SESSION_HANDOFF顶部及RUNBOOK。总体规划、RL、任务协议和控制参数保持原样。

## 2026-10-12：完整系统 launch 入口

用户要求减少启动终端。新增 src/lite3_navigation/launch/bringup.launch.py、scripts/bringup_runtime.py 和 rviz/navigation.rviz；已有 simulation/display launch 新增可选参数且原默认行为保留。lite3_gazebo 安装 maps，导航包安装新资源并补齐运行依赖。
完整入口自动播放 Gazebo，等待新鲜 /odom、12 关节与仿真时钟，启动阶段锁定速度，顺序配置/激活 map_server、planner_server、controller_server，用伪终端启动已有 RL 并发送原 z/c 状态切换，等待 ONNX ENTER 后请求 external。launch 捕获实际插件 Mode: external 日志确认接管，然后解除此次启动锁并启动常驻 mission_manager。未自动发送任务。
辅助 ROS 节点就绪后销毁，进程监管自己的 RL 并在退出时回收；UDP 端口占用拒绝新启动，重要子进程退出关闭本套系统。RL 源码/策略、Gazebo 插件、控制器参数、原任务/运动节点源码和 ARCHITECTURE/ROADMAP 未改。仍无雷达、临时障碍感知或重规划。
启动：source Jazzy 和工作空间后 ros2 launch lite3_navigation bringup.launch.py；另一个终端发送 /navigate_task。不与旧多终端入口并行。测试状态见文末/最新验证补充，不能把启动测试当作新路线行走验收。此次未提交或推送 Git。

## 最新进度（2026-10-10）

同步补充：用户要求把从开始至今的成果和开发过程完整保存到GitHub。已归档本任务541条可获取可见文字（191用户/350助手）、时间线、当前启动/交互/汇报素材、现存验证证据和实际依赖版本；不含图片附件、内部推理、工具原始输出或账号数据。历史讨论可能被后续修正，以当前源码/README/SESSION_HANDOFF为准。
外部RL6份快照与实际文件一致，指定上游补丁重放逐字节验证通过。build/install/log、虚拟环境、未修改第三方原仓库不上传；本次仅整理保存，不继续实现新功能。保留原规划和源码，目标PRIVATE仓库main，完整同步清单见SYNC_AUDIT及SNAPSHOT_MANIFEST。

最新补充：用户授权接入常驻任务Action。mission_manager已提供/navigate_task，串行异步状态机复用ComputePathToPose→完整Path→FollowPath；单任务忙碌拒绝，反馈/结果、实际map TF起点及到达检查、可选起点核对、steady总超时和主动取消清理均已接入。
取消/失败/超时先请求停止锁定并取消下游，确认终止后释放忙碌；清理无法确认则返回SYSTEM_ERROR并拒绝后续任务，晚到接受响应仍取消。不自动解除停止锁定；BLOCKED/MOTION_FAILED和重规划尚未实现。
旧单次源码原样另存mission_manager_once.cpp/可执行名mission_manager_once，两种入口择一运行；新入口收到旧goal_x等启动参数会明确报错。构建通过、独立ROS域178的16项模拟Nav2/TF/运动服务协议测试通过，以及旧入口指纹/启动提示检查通过；新Action入口实际Gazebo行走待用户验收。
本次没有启动实际Gazebo/RL或发运动指令，原controller配置和ARCHITECTURE/ROADMAP指纹不变，没有Git提交/推送。使用步骤、取消命令、参数及结果映射见src/lite3_navigation/README.md。/stop_task、状态查询、重规划、跌倒检测、地图/生命周期管理仍待实现。以下未接入Action文字为历史检查点。

### 较早接口包检查点（历史记录）

最新补充：用户授权助手建立任务接口包。已新增lite3_interfaces/action/NavigateTask.action（目标、结果、反馈）及构建/说明文件；构建、ROS2接口查询和三部分实际序列化往返检查通过。
仅定义格式，未新增常驻节点，未修改mission_manager或控制参数；/navigate_task服务端尚未实现，取消/起点检查/超时/重规划不能宣称完成。下一步沿原方案在现有mission_manager中接入该Action并复用已验证的规划/跟随流程。此次未发送任务，也未提交或推送Git。

用户确认仓库长路线成功，助手只读核对日志：mission_manager规划到(4,4)，465点，初始反馈剩余距离11.67m；控制器约43.8秒后到达，FollowPath状态4（SUCCEEDED）。验收后位置约(3.967,3.860)，目标位置误差0.144m。
用户已把controller.yaml转向速度保存为0.6 rad/s、max_angular_accel保存为12.0 rad/s²；助手保留这些值并补充注释、构建安装导航包。0.35原地转向未形成明显踏步，固定0.6测试通过；不称为测出了最低策略速度阈值。
此前486点/12.3m是另一条预览路线，不能混作成功任务；11.67m是初始剩余路线反馈，不是累计实际行走距离。
此次保存不发送移动任务，不提交或推送Git。下一步沿原方案完善持续等待终端任务的mission_manager、主动取消/停止协调、超时和结果分类；雷达后接。
原ARCHITECTURE/ROADMAP保持不变。以下旧状态仅为历史检查点；最新依据是SESSION_HANDOFF顶部。新任务前读取实际位置，不把重复目标的立即成功当作新运动验收。

### 同日较早检查点（历史记录）

最新接续补充：用户自行建立mission_manager的规划客户端，随后授权助手接入FollowPath。
现已编译并实测自动规划→完整Path交接→实际短直线行走；30点路线，前进约0.626m，目标误差0.182m，SUCCEEDED，程序退出0。
首次不动时RL仍在target mode 0；用户按z等待再c进入rl_control并重新external接管后通过，不归因于RViz勾选。
mission_manager目前每次执行一个终端参数目标后退出，没有自定义任务Action、主动取消、总超时、重规划、地图/生命周期管理；外部测试监测不算节点功能。
当前机器狗约(-3.378,-4.039)，不要把重复同一目标的立即成功当作新运动验收。
下一步仍分阶段验证转弯和绕货架，再补原任务管理功能；雷达后接，原ARCHITECTURE/ROADMAP保持不变。
下面的“mission_manager尚未完成/规划结果尚未衔接”是较早检查点，以SESSION_HANDOFF顶部为准。

最新补充：controller_server/local_costmap已按用户操作配置并启用，Twist输出重映射/nav_cmd_vel。
短直线FollowPath在0.20m/s时三次未取得进展；ROS运动节点确实接受导航速度，实际跟随尚未通过。
用户授权提高速度，controller.yaml期望速度与接近目标最低速度均调为0.32m/s，已构建并更新运行参数。
用户随后确认短直线正确；实际日志Reached the goal!、Action状态4(SUCCEEDED)，位移约0.61m，终点误差约0.19m且停止后位置稳定。
手工路线跟随闭环已通过；下一步衔接规划器返回Path与FollowPath，仓库绕行及mission_manager尚未完成。
0.32仍是短直线联调值；未测出RL最小运动速度，不把速度或虚拟网卡当作已确定根因。
下文“尚未配置/启动控制器”是较早检查点，以SESSION_HANDOFF顶部为准。整体规划保持不变。

用户已授权助手直接完成本步骤。lite3_motion_node 已接入 /nav_cmd_vel（Twist），
默认手动模式只接受 /cmd_vel，导航模式只接受 /nav_cmd_vel。
SetBool 服务 /lite3/set_navigation_mode：true 导航、false 手动；切换清除当前速度。
SetBool 服务 /lite3/set_stop：true 停止锁定、false 显式解锁；模式切换不能解除停止锁定。
解锁不会恢复已保存的旧速度，但正在持续发布的当前来源可以用新收到的消息重新驱动。
被拒绝的消息不刷新 0.5 秒 wall/steady 超时；原 UDP 协议、20Hz发送、/odom 和机身TF保留。
构建及独立 ROS 域的 18 项实际话题/服务/UDP 检查通过；测试未启动 Gazebo 或 RL。
复测脚本 src/lite3_control/test/check_motion_modes.py，运行前必须退出实际 RL 接收器及运动节点。
停止服务目前只锁定运动输入，没有取消 Nav2 Action；任务级停止/取消仍待实现。

2026-10-09 用户自行导入 large_warehouse 世界和配套地图，创建 lite3_navigation/config/planner.yaml。
用户已确认仓库内站立、RViz地图与位置对齐，以及 ComputePathToPose 到 (4,4) 的绕行路线。
统一 launch 已选择 large_warehouse，在(-4,-4,0.365)生成 Lite3，桥接同名世界时钟。
地图由临时 map_server 发布，map→odom 由临时零变换发布器提供；尚未合入原设计的任务/运动节点。
Nav2 控制服务器和 Regulated Pure Pursuit 已安装，尚未配置/启动路线跟随；机器狗尚未自主沿路线行走。
用户调整开发顺序为先场景、已知地图导航，再接雷达。原整体架构和最终功能要求不变。
下一步配置 controller_server/local_costmap，将 Twist 输出接 /nav_cmd_vel，再测试路线跟随；
不得让导航与手动速度争用 /cmd_vel，不把已算出路线称为已完成 A→B 自主行走。
当前不提交或推送 Git；下文较早状态均为历史检查点。

### 2026-10-08 检查点（历史记录）

2026-10-08 已新增真正的 `lite3_motion_node`：`/cmd_vel` 订阅、0.5秒超时归零、
20Hz本机UDP速度发送（127.0.0.1:30011、3个float vx/vy/wz）。编译及临时接收测试通过。
官方RL速度接收端也已实现，用 `./rl_deploy --ros-velocity` 启用，250ms断线归零，空格停止锁定/c恢复；默认键盘方式保留。
完整后台ROS2→RL→Gazebo验证约1.06米平地前进、停发和发送节点异常退出后停止。
用户已确认可见Gazebo中的ROS速度前进、转向和停止。统一启动已包含运动节点和桥接节点，
实际关节桥接到/joint_states、仿真时钟到/clock；仿真关闭滑块，显示节点用仿真时间。
后台关节→TF和时钟检查通过，用户已确认关节同步步骤正确。
位置反馈的nav_msgs/tf2_ros依赖已补齐，插件已发布原始机身状态，统一桥接已加入ROS /lite3/ground_truth/odom。
运动节点已从原始机身状态发布/odom及odom→base_footprint→TORSO，保留完整机身高度与倾斜；三包构建与后台实际运动验证通过。
仿真RViz的fixed_frame=odom，单独展示默认TORSO；用户可见整体移动效果待验收。map→odom、雷达/Nav2尚未实现。
下一步先解释并验收新增位置/TF，再按原M3接雷达；当前odom原点/轴等于Gazebo world，base_footprint投影在z=0。
用户需要清楚的中文解释与具体终端操作。详见SESSION_HANDOFF最新段落。

## 2026-10-04 检查点（历史记录）

已实现三个包、统一 Gazebo/RViz 启动、固定站立、Gazebo 与官方 RL 程序的 UDP 接口。
后台平地测试验证站立、前进约 2.15 米、空格停车、断线回退和 NaN 拒绝。
尚未实现自研 ROS2 运动节点、ROS2 `/cmd_vel` 输入、`/odom`、`/scan` 或 Nav2。
RViz 当前展示关节状态没有同步 Gazebo 实际关节运动。

当前：Gazebo 插件 ↔ UDP ↔ `rl_deploy`，后者用 ONNX Runtime 执行 `policy.onnx`。
Gazebo 与 MuJoCo 不互相通信；运行 Gazebo 控制时不要同时运行 MuJoCo。
`/lite3/control_mode` 当前是 Gazebo Transport 话题，不是 ROS2 话题。

用户在这个检查点要求暂停新功能开发，先完成保存。收到用户继续开发的请求后，
下一步仍为把运动功能接成规划中的 `lite3_motion_node`，实现 ROS2 速度输入、
零速度停止行走和速度输入超时归零；不要跳过运动验收直接实现导航。

## 本地检查、恢复与沟通

### 用户要求：终端操作手册持续同步（2026-10-13）

- `docs/TERMINAL_COMMANDS.md` 是独立、统一的日常终端交互操作手册。
- 后续每次新增或修改启动方式、CLI命令、服务/Action/话题、参数、单位、状态/错误信息，
  或取消/停止/模式切换规则，必须在同一次开发中同步更新该文档，再交付结果。
- 更新“最后更新”日期和文末记录；核对实际源码与已安装程序，不把未实现功能写成可用命令。
- 新源码尚需构建/重启才生效时必须注明。区分日常入口和单模块调试，避免重复运行节点。
- 每条命令写清终端、前置条件、作用、变量单位和退出方式，保留用户容易复制的完整命令。
- README/RUNBOOK等文档链接至该手册；后续AI接手同样遵守此维护要求。

- 用户是初学者，使用中文和具体解释；路径用绝对路径，不用波浪符号。
- 原机器路径是 `/home/ma/lite3_ws` 与 `/home/ma/Lite3_rl_deploy`。
  换机器先确定实际 checkout 和用户名，不能假定路径相同。
- 接手后先检查文件系统、Git 状态、已安装依赖和运行进程，保留用户新改动。
- 仅有 GitHub 内容也能理解设计和源码；完整运行仍需配置本机环境。
  外部原始仓库需按指定 commit 获取、应用已保存的补丁并重新编译。
- RL 的 6 个修改/新增文件、补丁、策略、准确版本和许可证已经保存，无需旧聊天恢复代码。
  build/install/log、虚拟环境、已启动进程和临时窗口不属于可恢复源码。
- 只把实际执行的检查称为本次验证；不要把旧记录称为在新电脑重新验证。
- 固定站姿回退不是自主起身，也不是尚未实现的 ROS2 速度超时停车。
- 当前授权允许整理相关成果；后续是否编辑代码或仅指导，遵循用户最新要求。
- 不删除源码、不覆盖运行中加载的动态库、不 reset/clean/force push；保留所有模型资源。
- 不复制整个第三方仓库，不提交凭据、生成文件或虚拟环境。GitHub 保持 private。
- 修改功能后同步更新 README 和 SESSION_HANDOFF 的实际进度，整体设计不随意重写。
