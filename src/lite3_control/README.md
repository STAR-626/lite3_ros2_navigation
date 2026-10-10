# Lite3 Gazebo 控制接口

本包提供加载在 Gazebo 内部的插件，以及新增的 ROS2 `lite3_motion_node`。
插件本身不另外创建 ROS2 节点。
默认使用固定站立控制；明确切换后，使用本机官方 `rl_deploy` 程序输出的关节指令。
演示时运行已训练策略的推理，不需要现场训练。

数据流程：Gazebo 机身/关节状态 → 本机 UDP → `rl_deploy` 和 `policy.onnx`
→ 关节目标角度/控制增益/前馈力矩 → 插件计算有上限的力矩 → Gazebo 物理仿真。

## 手动/导航模式与停止锁定（2026-10-10）

同一个 lite3_motion_node 现在有两种 Twist 输入，默认仅接受手动 /cmd_vel；
切到导航模式后仅接受 /nav_cmd_vel。两种来源不能同时控制，不增加节点。

在已启动运动节点、已 source 环境的空闲终端调用：

```bash
# 切到导航模式；false 切回手动模式。
ros2 service call /lite3/set_navigation_mode std_srvs/srv/SetBool '{data: true}'

# 停止并锁定，拒绝两个速度来源。
ros2 service call /lite3/set_stop std_srvs/srv/SetBool '{data: true}'

# 显式解除锁定；保留所选模式，等待新收到的速度。
ros2 service call /lite3/set_stop std_srvs/srv/SetBool '{data: false}'
```

切换模式、锁定或解锁都会清除保存的速度并立即发送零速度；模式切换不解除停止锁定。
解锁不会自动恢复保存的旧目标；当前来源若仍持续发布，下一条收到的消息可以重新驱动。
未选中的来源和停止锁定期间的消息不刷新0.5秒实际时间超时计时。
重启回到默认手动、未锁定、零速度。Twist 无生成时间戳，接收时无法证明网络延迟消息的原始年龄。
节点必须搭配 RL 的 --ros-velocity 方式；原默认键盘控制方式不会经过此 ROS 输入锁定。
服务本身只锁定本层速度，不负责取消Nav2 Action；现有常驻mission_manager已接入任务级取消/停止协调，见导航包README。新任务入口实际Gazebo行走/取消仍待验收。

构建通过，18项独立ROS域的实际话题/服务/UDP测试通过；未运行 Gazebo/RL 运动。
复测需要退出已有运动节点与 RL 接收器，空出30011端口：

```bash
source /opt/ros/jazzy/setup.bash
source /home/ma/lite3_ws/install/setup.bash
python3 /home/ma/lite3_ws/src/lite3_control/test/check_motion_modes.py
```

脚本启动真实安装后的运动节点，使用独立ROS_DOMAIN_ID=179，验证来源互斥、锁定/解锁、
切换清零、无效数字、限幅、两种模式超时、冻结仿真时钟、原odom/TF及退出/重启行为。
日志写入/tmp，结束后回收自建进程及UDP端口。该段记录的是运动模式接口测试；后续已接入Nav2路线跟随，最新状态见根README。

## 启动步骤

先在旧的启动终端按 Ctrl+C，关闭已有 Gazebo / RViz，再构建，避免覆盖正在加载的动态库。

以下先保留官方键盘调试方式；新增ROS2速度方式已接入RL，见本文末尾。

终端 1：

```bash
source /opt/ros/jazzy/setup.bash
cd /home/ma/lite3_ws
colcon build --packages-select lite3_description lite3_control lite3_gazebo
source /home/ma/lite3_ws/install/setup.bash
ros2 launch lite3_gazebo simulation.launch.py
```

点击 Gazebo 播放按钮，确认固定站立。当前统一仿真使用仓库场景、实际关节状态、
机身里程计与TF；RViz中地图和map→odom仍需手动启动，见根README。

终端 2（外部部署项目需事先完成其官方依赖安装和编译）：

```bash
cd /home/ma/Lite3_rl_deploy/build
./rl_deploy
```

按 `z`，至少等待 4 秒，再按 `c`。确认打印 `standup_state ... rl_control`
和 `PolicyRunner entered`。此时控制程序已进入 RL，但插件仍固定站立。
不要同时运行 `mujoco_simulation.py`，它与插件占用同一个 UDP 端口。

终端 3，把 Gazebo 的关节控制权交给外部程序：

```bash
source /opt/ros/jazzy/setup.bash
gz topic -t /lite3/control_mode -m gz.msgs.StringMsg -p 'data: "external"'
```

确认 Gazebo 终端打印 `Mode: external`。回终端 2 连续按两三次 `w` 尝试前进，
按空格把运动命令归零。松开按键不等于停车，这是官方程序的速度增量输入方式。

退出接管时，先在终端 3 执行：

```bash
gz topic -t /lite3/control_mode -m gz.msgs.StringMsg -p 'data: "stand"'
```

确认 `Mode: stand (requested)`，再在终端 2 按 Ctrl+C 退出控制程序。

## 协议和保护

- 插件仅绑定 `127.0.0.1:20001`，收取 60 个 float（240 字节）的控制包。
- 状态发送至 `127.0.0.1:30010`：1 个 double 时间戳和 45 个 float，共 188 字节。
- 关节顺序：FL、FR、HL、HR；每条腿 HipX、HipY、Knee。角度使用弧度。
- 机身转动速度和加速度使用机身坐标系。静止直立时加速度 Z 约为 +9.81。
- 状态中的力矩字段为插件施加的力矩，不是独立传感器测量值。
- 只有新鲜有效且所有关节 Kp 大于零的指令才允许切换 `external`。
- 错误格式、NaN 或超过 250 毫秒无有效指令，退回 `stand`；重新接管需明确切换。
- 髋关节力矩限制为 ±24 N·m，膝关节 ±36 N·m，与当前 URDF 一致。
- 固定站立不具备自主起身或跌倒恢复能力。

## 验证范围

2026-10-04 独立后台 Gazebo 平地测试通过：状态包、控制切换、断线回退、NaN 拒绝，
以及现有策略的站立、前进和空格停车。一次前进约 2.15 米，未触发姿态保护。
台阶、崎岖地形和长期稳定性尚未验证。

用户已确认可见ROS速度前进、转向和停止。统一启动已接入实际关节与时钟桥接；
现已接入/odom和机身TF；用户已确认仓库地图与全局路线，导航速度入口已实现，
后续旧单次入口路线跟随已实际通过短直线与仓库长路线，常驻任务Action也已通过隔离测试；LiDAR `/scan`、动态障碍和完整任务管理仍待实现。
本包不会自动下载策略，也不会复制整个第三方部署仓库进工作空间。

## 实际机身状态订阅（2026-10-08）

统一桥接将Gazebo /lite3/ground_truth/odom转换为ROS nav_msgs/msg/Odometry。
同一个lite3_motion_node订阅该话题，校验输入后发布平面/odom及odom→base_footprint→TORSO。
odom与Gazebo world原点/轴一致，base_footprint为z=0平面导航参考；完整机身高度、倾斜保留在第二段TF。
机身速度先转世界再转导航轴，转向速度按实际yaw变化率换算。位姿及TF使用原始仿真时间戳。
输入格式/数字/朝向无效时跳过，不重复旧位置；接近竖直时跳过不可可靠的平面投影。
协方差默认零，仅为本阶段仿真真值；map→odom和定位异常的任务级处理尚未实现。
统一仿真下运动节点使用仿真时间，速度发送与0.5秒输入超时仍用实际时间。RViz固定参考为odom。
独立数学/ROS边界及实际RL运动测试通过，原始位置与TF组合一致，四足可连到odom，停发后停止行走。

启动统一仿真并点击播放，可在空闲已source终端检查：

```bash
ros2 topic echo /odom --once
ros2 run tf2_ros tf2_echo odom TORSO
```

第二条持续打印机身相对odom的位置关系，Ctrl+C结束查看；不控制机器狗。

## ROS2 速度发送端（2026-10-08）

统一仿真launch已自动启动该节点，不要重复运行。仅单独调试发送端时使用：

```bash
source /opt/ros/jazzy/setup.bash
source /home/ma/lite3_ws/install/setup.bash
ros2 run lite3_control lite3_motion_node
```

订阅 `/cmd_vel` 与 `/nav_cmd_vel`，类型 `geometry_msgs/msg/Twist`，按模式选择其中一个；
使用 linear.x、linear.y、angular.z。默认手动模式，停止锁定优先于来源选择。
每50毫秒向本机 `127.0.0.1:30011` 发送3个32位float，共12字节：vx、vy、wz。
这是同一主机上的原生float协议；临时Python接收可用 `struct.unpack('=3f', data)`。
vx/vy单位米/秒，wz单位弧度/秒，发送实际速度而非策略内部的归一化比例。
每个使用分量限制为±0.8；用于与现有策略尺度对齐，不代表任意地形都能安全执行此上限。

初始无指令及超过0.5秒无当前允许来源的有效ROS消息时，持续发送零速度；
当前来源无效数值拒绝并归零，非当前来源及停止锁定期间的数据忽略。
正常退出时尽力发送一次零速度。UDP发送成功不等于对端确认收到；接收端仍需独立断线保护。
执行 `./rl_deploy --ros-velocity` 时官方程序已监听30011；临时接收器必须退出以释放该端口。
30011的速度包与20001的240字节关节包不同，不可互相发送。

另一个已source的终端可以发布：

```bash
ros2 topic pub --rate 10 /cmd_vel geometry_msgs/msg/Twist '{linear: {x: 0.2}, angular: {z: 0.0}}'
```

临时接收器绑定127.0.0.1:30011后应收到0.2/0/0；停止ROS发布约半秒后应收到0/0/0。
独立后台测试已验证启动零速度、持续更新、超时、三个分量、限幅、NaN/Inf拒绝和正常退出。
此接口不增加新的ROS节点。独立后台已验证完整ROS2→RL→Gazebo前进和停止，原9节点规划不变。

## ROS 速度实际控制

1. 启动Gazebo、播放，确认固定站立。
2. 统一仿真已启动运动节点，不再重复运行；仅单独调试发送端时使用 ros2 run。
3. 控制终端在 `/home/ma/Lite3_rl_deploy/build` 执行 `./rl_deploy --ros-velocity`，按z等待至少4秒再c。
4. 在已source的终端用本文已有 `gz topic ... external` 命令切换，再持续发布 `/cmd_vel`。

默认先测试vx=0.3、vy=0、wz=0。停发ROS消息约0.5秒后目标速度归零；发送节点突然退出时，
接收端250毫秒未收到速度包归零。控制终端空格锁定停止，c显式恢复；移动按键禁用。
正常退出前先切回 `stand`，再关闭控制程序。固定站姿不保证从任意倒地状态恢复。

2026-10-08后台平地测试以vx=0.32移动约1.06米，停发消息后停止；强制结束测试发送节点后
由接收端断线保护停止。没有NaN或姿态保护触发。尚未验收可见窗口、长期运行或复杂地形。
