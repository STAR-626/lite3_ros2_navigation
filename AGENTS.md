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

## 固定方案，除非用户明确修改

- Ubuntu 24.04、ROS2 Jazzy、Gazebo Harmonic；Gazebo 演示，RViz 辅助观察。
- 用户通过终端操作；预先制作与 Gazebo 一致的地图，第一版使用仿真实际位姿。
- 开源 RL 负责基础移动，Nav2 负责路径规划和避障；演示执行策略推理，不现场训练。
- 精简设计约 9 个节点，原约 11 节点备用方案保留。package、进程和节点不要混为一谈。
- 手动 `/cmd_vel`、导航 `/nav_cmd_vel` 和停止锁定需要互斥。
- 轻度起伏必须实测；SLAM、危险地形理解、移动障碍和完整自训练流程属于后续。
- 最终任务结果及起点检查沿用原架构，不替换为新的任务方案。

## 2026-10-04 检查点

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
- RL 的 3 个修改文件、补丁、策略、准确版本和许可证已经保存，无需旧聊天恢复代码。
  build/install/log、虚拟环境、已启动进程和临时窗口不属于可恢复源码。
- 只把实际执行的检查称为本次验证；不要把旧记录称为在新电脑重新验证。
- 固定站姿回退不是自主起身，也不是尚未实现的 ROS2 速度超时停车。
- 当前授权允许整理相关成果；后续是否编辑代码或仅指导，遵循用户最新要求。
- 不删除源码、不覆盖运行中加载的动态库、不 reset/clean/force push；保留所有模型资源。
- 不复制整个第三方仓库，不提交凭据、生成文件或虚拟环境。GitHub 保持 private。
- 修改功能后同步更新 README 和 SESSION_HANDOFF 的实际进度，整体设计不随意重写。
