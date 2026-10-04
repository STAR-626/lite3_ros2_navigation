# 接续开发记录（2026-10-04）

用户本次明确暂停新功能开发，先同步全部有效成果到 private GitHub。
整体方案沿用 ARCHITECTURE.md / ROADMAP.md，不能因上下文切换重新设计节点或改变项目目标。

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
