# 原生工具闭环验证（2026-10-20）

- unit_checks.txt：89项离线单元（原79+原生工具协议10），7组CTest通过。
- agent_protocol.json：域224，已安装后台＋模拟原生模型/场景/Nav2的8项检查：完整句子与空间目录输入、get_environment→东墙→货架1→本轮出发处、上一轮第二对象指代、查询后全部删点、网络等待时本地查询/停止、取消后续腿、失败后拒绝模型排队运动、未知Shell工具整批拒绝、失联迟到结果隔离（部分合并为一项）。
- native_chain.json：域222，真实Gazebo仓库＋真实Smac Lattice/full-footprint costmap，东墙→货架1→出发处三腿规划与临时目标接口衔接。使用合成PGM地图发布/TF、静态/膨胀层及替身NavigateTask；没有雷达层、控制器或真实运动。
- legacy_regression.json / rules_regression.json：旧JSON模型入口13项及规则入口13项回归通过。
- approach_regression.json：原临时接近协议11项回归通过。
- source_hashes.json：验证时相关源码SHA256。

所有模型输出是测试替身；HTTP适配器用虚构密钥及假HTTP响应单元验证。没有读取用户密钥、付费调用、机器狗/RL、整机导航验收。
实际DeepSeek是否理解每一种措辞需要用户在线测试；不能把替身的语言选择当成真实模型能力测量。
另外手动检查：长轮次工具历史压缩后保留函数名/参数/结果；安装脚本与源码一致；launch默认agent_tools=true。
