# GitHub同步审计（2026-10-19）

## 仓库和范围

本地/home/ma/lite3_ws，origin=https://github.com/STAR-626/lite3_ros2_navigation.git，
PRIVATE、main，账号/作者STAR-626 <hanchao.ma@outlook.com>。
fetch后本地HEAD与origin/main均为580ac460d1a1801e08d930fcad3140083da3a19b，无分叉。
本轮用户明确授权同步最近全部成果并检查仓库；正常提交/推送，保留历史，不force。
旧审计、清单、manifest按2026-10-17日期归档到development_history。

保存六包源码、GUI、配置、测试、STL/URDF、世界/地图/RViz，外部RL六份快照/补丁/策略/许可，
开发过程说明和精选验证证据。PROJECT_FILES/PROJECT_TREE/manifest按当前Git有效候选重新生成。
本轮未导出最新全部聊天原文；原541条历史文字仍只覆盖10月1日至10月10日。
不复制整个deep_robotics_model、整个外部RL原仓库、浏览器、凭据或用户截图聊天背景。

## 文档检查和修正

- 增加CURRENT_ARCHITECTURE，准确解释Lattice/Omni/Rotation Shim/MPPI/RPP、点云与执行链路。
- 增加KNOWN_ISSUES：用户报告多箱遮挡下全局记录波动与反复换路，根因未确认、未修复。
- README纠正“后台优化是下一步”等过期说明，区分较早实走与随后候选配置的验证范围。
- 旧整体架构/路线不重写，增加当前状态入口；新自然语言接口只作为后续计划记录。
- 导航包、操作/进度、交接和开发日志同步当前保护轮廓0.94×0.50m和待验收限制。
- 补齐新电脑显式Rotation Shim依赖；第三方说明修正默认Omni原语/备用diff。
- 当前文档相对链接检查；冻结旧README迁目录后遗留相对链接和历史对话占位链接不改原文，
  新增HISTORICAL_LINKS说明和当前入口。历史证据保持原内容与当时“未提交”状态。

## 检查结果与验证边界

- 全部有效候选（包括gzip解压内容）扫描常见私钥、GitHub/API/云密钥签名及带密码认证URL，未发现匹配；
  敏感文件名检查无候选。自动扫描不是绝对无敏感信息保证。
- 没有根build/install/log候选、嵌套Git或符号链接；.gitignore覆盖生成目录/缓存/IDE/临时/本地.env。
- 最大文件shank.STL，1,352,184字节；无超过10MiB候选，不需要LFS。
- 四份STL及Lite3_original保留。外部RL六份本机源码/归档SHA与UPSTREAM.json一致，策略SHA一致。
  外部原仓库额外生成MUJOCO_LOG.TXT/.venv不复制。
- 2026-10-19重跑感知28项单元测试全部通过；39个Python、44个JSON、7个YAML、
  10个XML、3个URDF、6个SDF候选解析通过（新增审计元数据不计入这次前置统计）。
- git diff --check通过。已有GUI/物理、清除、路线优化证据一并保存，不把历史结果写成本次重跑。
- 用户Gazebo/RL仍在运行，本次没有重建覆盖加载库、重启、运动指令或占用实际控制UDP。
  没有重跑完整动态导航；障碍闪烁仍未修复。

## 许可和恢复

模型/外部部署BSD-3-Clause、仓库场景/地图MIT、派生GUI配置Apache-2.0及项目插件许可保留，
见THIRD_PARTY_NOTICES。策略未发现额外权重条款，继续private；未来public前重查，
旧description/gazebo包自身许可证TODO仍未擅自替用户选定。

新电脑按README的Jazzy依赖/rosdep/colcon和external/lite3_rl_deploy/README的固定版本/补丁恢复。
本次没有在全新电脑从零安装验证；不能仅复制install或认为仓库已包含系统运行环境。
提交后以GitHub远端main和本地HEAD一致、Git工作区干净、远端树清单/manifest一致为完成条件。
