# AI 接手入口：先读记录，再继续开发

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
