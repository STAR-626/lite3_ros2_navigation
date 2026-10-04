# Lite3 Gazebo 控制接口

本包提供加载在 Gazebo 内部的插件，不另外创建 ROS2 节点。
默认使用固定站立控制；明确切换后，使用本机官方 `rl_deploy` 程序输出的关节指令。
演示时运行已训练策略的推理，不需要现场训练。

数据流程：Gazebo 机身/关节状态 → 本机 UDP → `rl_deploy` 和 `policy.onnx`
→ 关节目标角度/控制增益/前馈力矩 → 插件计算有上限的力矩 → Gazebo 物理仿真。

## 启动步骤

先在旧的启动终端按 Ctrl+C，关闭已有 Gazebo / RViz，再构建，避免覆盖正在加载的动态库。

终端 1：

```bash
source /opt/ros/jazzy/setup.bash
cd /home/ma/lite3_ws
colcon build --packages-select lite3_description lite3_control lite3_gazebo
source /home/ma/lite3_ws/install/setup.bash
ros2 launch lite3_gazebo simulation.launch.py
```

点击 Gazebo 播放按钮，确认固定站立。当前 RViz 使用模型展示和 GUI 关节状态，
尚未同步 Gazebo 的实际关节运动。本步骤在 Gazebo 中观察运动。

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

下一阶段：ROS2 `/cmd_vel`、`/odom`、真实关节状态同步、LiDAR `/scan` 和 Nav2。
本包不会自动下载策略，也不会复制整个第三方部署仓库进工作空间。
