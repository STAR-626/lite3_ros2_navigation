# 临时物体接近验证（2026-10-20）

- unit_checks.txt：79项离线单元（原67+接近几何12），6组CTest全通过。
- native_planner.json：隔离域222，真实已安装Gazebo仓库和Smac Lattice规划器/costmap验证4项：关闭开关拒绝、不自动开导航；真实可达候选→原NavigateTask接口目标；不写长期地点；地图南侧/0.5m间距约束。
  此用例使用原静态PGM经合成地图发布、合成机器人TF、只启用静态/膨胀层，NavigateTask为测试替身，未启用雷达障碍层/控制器/机器狗/RL。
- approach_protocol.json：隔离域223，模拟场景/规划器/任务/模型验证11项：关闭开关、未知全阻塞图、旧地图、首候选不可达回退、不持久化、停止、迟到接受、计算/执行中物体移位、错误终点、超时、心跳丢失。
- semantic_regression.json：原真实Gazebo语义目录10项回归通过。此fixture没有导航参数/地图/规划接口，因此物体导航请求仍在接口未就绪时拒绝；不表示新增接近功能不支持。
- deepseek_regression.json / rules_regression.json：原模型入口13项、规则入口13项回归通过。
- source_hashes.json：本次相关源码SHA256。

所有测试均未读取密钥、未发真实API请求、未启动机器狗/RL或进行整机行走。
真实模型措辞、默认全感知costmap下机器狗实际接近仍待用户验收。未声称路径最短、任意物体/动态模型均能接近或完成视觉巡检。
