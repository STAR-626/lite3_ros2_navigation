# DeepSeek执行接入：2026-10-20

用户此前实际API预览、缺参数澄清和不支持任务拒绝验证正常。本轮未读取真实密钥、未发真实API请求，也未启动机器狗/RL。

- unit_checks.txt：三个CTest程序，内部共35项Python检查（规则/存储16、DeepSeek协议16、工作线程3）。
- model_execution_protocol.json：域220、隔离Gazebo分区，生产安装后的后台以测试脚本加载，测试临时替换interpret函数为合成响应；生产代码没有测试模型/任意API端点参数。10项执行协议检查通过：存点、澄清/拒绝/坏输出/API失败不执行、依次Action、慢请求可本地查状态/停止、关闭会话丢弃迟到结果、执行资格期限、地点快照变化、心跳失联、禁止模型代确认、停止活动任务与队列。
- rules_regression.json：新版后台回归原规则入口13项，包括实际console输入/退出/Ctrl+C、迟到Action接受和断线。
- launch_arguments.txt：language_mode和ai_control参数可见；不是完整bringup实走证据。
- source_hashes.json：相应最终源码SHA256；安装后的后台、console、解析器和worker与源码逐字节一致。

超时用例在测试脚本中缩短请求资格期限以快速验证失效逻辑，生产仍为30实际秒；测试不声称等待/测量了真实API超时。当前请求线程为守护线程，不能因本地停止保证上游HTTP已经取消，只保证旧结果不再进入执行。

原始日志保留在结果JSON所写的/tmp目录，可能被系统清理；此处不伪装保存了完整原始bag。完整真实DeepSeek＋Gazebo机器狗/RL导航由用户按docs/DEEPSEEK_EXECUTION.md复测。整体模型、规划器、控制器和原节点分工不变，无新增ROS节点；没有提交或推送Git。
