# 规则交互入口验证：2026-10-20

本轮未接模型/API，未下载模型或写入密钥，未启动机器狗/RL。没有提交/推送Git。

- unit_checks.txt：16项规则、数字/角度、地点文件、地图指纹、参数缺失/非法、队列坐标快照检查；CTest interaction_core通过。
- backend_protocol.json：域218，真实安装后的后台与console，模拟已有任务Action和总开关/状态服务，13项协议检查：地点保存/覆盖、缺点整组拒绝、三目标逐个成功推进、失败终止、忙时查询/停止、断线、重复请求、停止后的迟到接受、重新连接、删除、正常退出与Ctrl+C停止确认。
- gazebo_markers.json：域219、独立Gazebo GUI MarkerManager与真实GPU雷达，5项检查通过。标记实际登记、中文标签转成Ogre2支持的线几何、GUI球体不增加雷达命中、不创建world模型、删除后图形管理器中不再有地点圆环/标签/箭头。
- gazebo_marker_ids.txt：真实图形管理器返回的ns/id列表。该接口只返回标识，不能把它当成完整几何记录；测试另通过辅助进程--audit输出核对发送的字形线几何及GUI可见性，并检查GUI没有Invalid Marker type错误。
- launch_arguments.txt：新增ai_control和places_file参数可见；没有据此宣称完整bringup已跑通。
- source_hashes.json：对应最终源码SHA256。

开发中检查并修正：rclpy Node已有只读handle属性，动作句柄改用goal_handle；无GUI的服务端没有GUI MarkerManager，因此真实标记验证增加独立GUI；Ogre2不支持原生TEXT，改用Qt字体轮廓的LINE_LIST；console使用自有Ctrl+C处理，保持ROS上下文到停止确认完成。

正式地点文件没有修改，测试地点只在结果JSON的/tmp目录。原始日志与发送审计可能随/tmp清理；本目录保存有界摘要，非原始rosbag。完整机器狗＋RL的顺序导航实走仍待用户按NATURAL_LANGUAGE_CONTROL.md验证。
