# GitHub 同步前检查（2026-10-04）

本次只保存已有成果和接续说明，暂停新功能开发。目标仓库 STAR-626/lite3_ros2_navigation，PRIVATE，main；远端同步前与本地已有历史一致，没有覆盖他人提交。

## 扫描范围与完整性

完整递归扫描 /home/ma/lite3_ws（包含隐藏文件，Git内部元数据单独排除），并检查本机相关目录 Lite3_rl_deploy 和 deep_robotics_model。
初次扫描 workspace 有 26 个有效普通文件；生成目录 build 223 个文件、install 88 个文件、log 142 个文件，全部排除。
外部 RL 项目除虚拟环境之外没有未跟踪的自建文件；3个修改源码全部备份。另1个修改文件 MUJOCO_LOG.TXT 是生成日志，保留在本地但不提交。
两个官方模型来源目录没有未保存源码修改。项目有效源码/资源没有外部符号链接。

初次快照保存 37 个文件；补充根目录 AI 接手入口后共 38 个文件，全部清单如下；Git不保存空目录。目录概要见根 README。此次补充只更新文档，原架构与功能代码保持不变。

```text
.gitignore
AGENTS.md
README.md
THIRD_PARTY_NOTICES.md
docs/ARCHITECTURE.md
docs/ROADMAP.md
docs/SESSION_HANDOFF.md
docs/SYNC_AUDIT.md
external/lite3_rl_deploy/LICENSE.DeepRoboticsLab.txt
external/lite3_rl_deploy/README.md
external/lite3_rl_deploy/UPSTREAM.json
external/lite3_rl_deploy/patches/local-simulation-fixes.patch
external/lite3_rl_deploy/policy/ppo/policy.onnx
external/lite3_rl_deploy/requirements-mujoco.txt
external/lite3_rl_deploy/snapshots/interface/user_command/keyboard_interface.hpp
external/lite3_rl_deploy/snapshots/run_policy/lite3_test_policy_runner_onnx.cpp
external/lite3_rl_deploy/snapshots/state_machine/rl_control_state_onnx.hpp
src/lite3_control/CMakeLists.txt
src/lite3_control/LICENSE
src/lite3_control/README.md
src/lite3_control/package.xml
src/lite3_control/src/lite3_gazebo_interface.cpp
src/lite3_description/CMakeLists.txt
src/lite3_description/LICENSE.DeepRoboticsLab.txt
src/lite3_description/launch/display.launch.py
src/lite3_description/meshes/hip.STL
src/lite3_description/meshes/shank.STL
src/lite3_description/meshes/thigh.STL
src/lite3_description/meshes/torso.STL
src/lite3_description/package.xml
src/lite3_description/rviz/lite3.rviz
src/lite3_description/urdf/Lite3.urdf
src/lite3_description/urdf/Lite3_gazebo.urdf
src/lite3_description/urdf/Lite3_original.urdf
src/lite3_gazebo/CMakeLists.txt
src/lite3_gazebo/launch/simulation.launch.py
src/lite3_gazebo/package.xml
src/lite3_gazebo/worlds/lite3_empty.sdf
```

## 忽略或不复制的内容

- 工作空间根 build/、install/、log/：生成文件，不进入Git。
- __pycache__/、*.py[cod]、.pytest_cache/、.venv/、venv/、.cache/、.colcon/。
- .vscode/、.idea/、编辑器交换文件、备份尾缀、.DS_Store、Thumbs.db。
- .env及其本地变体；示例.env.example/.env.sample允许保留，提交前仍检查内容。
- 外部原始仓库的.git、整套第三方依赖、SDK/ONNX二进制库、虚拟环境、生成日志不复制。
- deep_robotics_model原始仓库不整体上传。

四个STL、三份URDF、RViz、launch、world和policy.onnx均未被忽略规则排除。

## 文件体积与敏感信息检查

全部候选文件检查：没有达到50 MiB的文件，不需要Git LFS。
最大文件shank.STL为1352184字节；策略文件758441字节。
对全部文本候选文件（包括补丁/快照/文档）检查私钥标记、GitHub/AWS/OpenAI凭据样式、常见密钥/密码赋值和敏感文件名，未发现匹配。
模型与策略是明确列出的二进制资源，按来源、路径和校验值检查；自动扫描不构成绝对无敏感信息保证。
没有复制账号凭据、浏览器/代理数据、SSH私钥、Git配置或构建环境日志。

## 许可与规划

模型和部署项目的原始BSD 3-Clause许可已保留，来源明确注明DeepRobotics / DeepRoboticsLab。
未发现策略权重另附独立许可声明，保持PRIVATE；以后公开前需再次核实补充条款。
两个原有package的License TODO没有被擅自替换，lite3_control保留自己的LICENSE。

ARCHITECTURE.md SHA256：67f8abac558d4201a65df89f40f5ae4a7c8590359ffc38f26d8f218cb057ddc8。
ROADMAP.md SHA256：73571ba5f74184f8aad752b34c2f3c161f4ecc6a25cf63628dd2291940eb3e08。
这两份整体规划原文未变。README更新实际进度和使用方法，新建SESSION_HANDOFF保存接续开发上下文。

## 验证

- 三份外部修改从指定上游原文件应用补丁后，与本机及保存快照逐字节一致。
- ONNX策略SHA256与记录一致，原始上游策略未修改。
- src下全部package/XML/URDF/SDF可解析，Python launch语法可解析。
- 既有Gazebo编译、站立/前进/停车、断线回退和NaN拒绝证据记录在SESSION_HANDOFF。
- 本次同步没有重新运行GUI或继续实现cmd_vel，也没有把平地测试夸大为导航/复杂地形验收。
- 最终提交前再次核查暂存文件完整性、无删除、无生成目录；push后核对远端commit。

提交前Git变化：原模型/仿真依赖及world修改、新增control包、Gazebo模型和统一launch，以及本次文档/外部成果保存。已有Git历史保留，不reset、不clean、不force push。
