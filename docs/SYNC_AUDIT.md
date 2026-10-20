# GitHub同步审计 2026年10月20日

## 仓库与授权

目标为 https://github.com/STAR-626/lite3_ros2_navigation 的main分支。
同步前本地HEAD与origin/main均为14d56d957308d01c70de8b46f71cfe7226218443，fetch确认没有分叉。
GitHub实际为PUBLIC；用户本轮明确要求“保留公开并上传”，覆盖历史保持private要求。
采用正常提交与推送，不重写或强推历史。此前审计与文件清单已按2026-10-19归档。

## 本次保存内容

保存10月20日的遮挡清除确认、场景五模型清理、规则交互入口、DeepSeek预览与正式入口、
多轮上下文、环境语义目录、货架编号、物体临时接近及原生工具调用闭环。
保存对应源码、参数、测试、精选验证证据、操作手册、架构、已知问题及接续记录。
两份课程Word报告放入docs/reports，桌面原件保留。没有重新导出完整聊天历史或复制用户截图背景。

## 验证与审查

- 本轮7组AI单元测试（89项）通过，感知occlusion_evidence测试通过，git diff --check通过。
- 全量候选Python语法、JSON/YAML/XML/URDF/SDF解析通过。
- 常见密钥签名扫描包含gzip解压内容及两份Word内XML，未发现匹配；不读取仓库外真实凭据。
  自动扫描有边界，不等于绝对无敏感信息保证。
- 无build/install/log、虚拟环境、符号链接或超过10MiB文件；模型资源与许可继续保留。
- 外部RL六份修改/新增源码与snapshots逐字节及UPSTREAM.json哈希一致，策略SHA一致。
  本次无需更新补丁，不向DeepRoboticsLab上游推送，也不保存MuJoCo生成日志或.venv。
- manifest记录当前有效文件的SHA256；自身哈希排除，避免循环。文件清单和目录树一并更新。

## 实际验证边界

本次同步没有调用真实DeepSeek、重新启动Gazebo/RL或执行导航运动；此前隔离验证证据按原范围保留。
原生工具默认入口、临时目标与固定几何限制见AI_TOOL_AGENT.md、OBJECT_APPROACH.md和KNOWN_ISSUES.md。
不把替身Action或静态图规划测试称为全感知机器狗实走；此前“未提交/private”记录保留为历史状态。

## 新电脑恢复

按README与external/lite3_rl_deploy/README安装依赖、获取固定上游版本、应用补丁并重新构建。
用户自行配置仓库外DeepSeek密钥；用户本地保存点、语义编辑与会话不自动同步。
货架默认中文编号来自源码，新环境无需复制本机私有地点。无AI模式和rules模式保留。
本次没有在全新电脑从零恢复验证。完成条件为远端main提交与本地HEAD一致、工作区干净。
