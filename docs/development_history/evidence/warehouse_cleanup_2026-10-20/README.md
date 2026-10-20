# 仓库模型永久清理验证（2026-10-20）

删除两个destination_marker和三个box_obstacle模型，保留其他世界元素；源文件修改前保存于仓库外备份目录，绝对路径见result.json。

- result.json：模型删除列表、其余世界元素语义等价检查、原地图完整包围框空闲格核对、地图哈希、安装一致性及独立场景检查结果。
- scene.txt：隔离GZ_PARTITION中已安装世界的实际scene/info回执；不包含机器狗或RL。
- scene_check.log：隔离Gazebo服务器输出。
- `gz sdf -k`：已安装SDF返回Valid。

地图本身没有这五个模型的占据，故PGM/YAML未改动，并未重新生成整张静态地图。未验证完整导航任务；未向用户运行域发送命令。
