# 接续开发记录（最新更新 2026-10-10）

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
