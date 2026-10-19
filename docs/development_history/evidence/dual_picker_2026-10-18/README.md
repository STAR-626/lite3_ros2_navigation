# 两用Gazebo面板验证：2026-10-18

result.json汇总；ctest.log为真实CTest输出。两项测试共约14.3实际秒通过。

1. target_picker_interaction：真实QML和Qt/Gazebo事件，模拟create/remove/scene服务并延迟场景确认；
   原选点、拖动/高度/NaN拒绝、坐标复制、导航原消息保留；新增尺寸、只创建专属箱体、确认后控制、
   WASD/自动重复释放、斜向限速、松键/空格/失焦/切页/插件关闭停车、仅删除自有模型。
2. picker_box_physics：真实孤立Gazebo Physics、UserCommands、SceneBroadcaster世界，无机器狗/RL；
   GUI生成实体箱子，原生VelocityControl与服务端guard加载，位移、碰撞记录及不可穿墙、旋转后世界轴、
   指令流消失后停车、移除保留其他模型全部通过。

面板预览来自离屏Qt测试，不是用户真实Gazebo场景截图。未运行完整机器狗导航/动态避障验收。
编译初期同库多翻译单元使用Register.hh造成重复插件入口，辅助系统改用RegisterMore.hh解决。
原有BoxContacts与CLI箱子控制代码保持，新增系统与其同库注册。
