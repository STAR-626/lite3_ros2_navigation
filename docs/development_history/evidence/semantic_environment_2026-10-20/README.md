# 环境语义目录验证（2026-10-20）

- unit_checks.txt：67项离线单元检查（原51+环境16），5组CTest全通过。
- environment_protocol.json：ROS域221、独立GZ分区、真实已安装仓库世界＋已安装交互后台10项验证；无机器狗/RL。目录17货架与4墙、模型移动位姿、运行时创建/删除、标注重启保留、已有地点类别/别名、禁止物体中心导航、模拟模型收到语义数据并执行白名单查询/标注、元数据改变使迟到模型结果失效、场景不可用不返回旧位置。
- deepseek_regression.json：原模型入口13项协议回归通过。
- rules_regression.json：原规则入口13项协议回归通过，含实际ai_console/Ctrl+C。
- source_hashes.json：验证时相关源码SHA256。

模型和HTTP响应都是测试替身，未读取用户密钥、未调用付费API、未启动机器狗/RL或进行整机行走。
真实API措辞和完整bringup演示仍待用户验收。临时原始日志路径在各result的out字段；用户地点和语义标注文件未复制到仓库。
