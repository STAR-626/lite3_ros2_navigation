# Gazebo导航与动态障碍两用面板

## 启动和找到面板

本次已经构建。退出旧系统后，在正常终端执行：

```bash
source /opt/ros/jazzy/setup.bash
source /home/ma/lite3_ws/install/setup.bash
ros2 launch lite3_navigation bringup.launch.py
```

面板标题为“Lite3 导航与动态障碍”，加载标识仍为Lite3TargetPicker。
如果关掉面板，通过Gazebo右上角插件菜单查找并添加Lite3TargetPicker。
面板可滚动，窗口较小时往下滚动查看提示。不要重复添加多个面板来控制同一只箱子。

## 导航目标页

先按原流程开启导航总开关；点击“选择目标”，再点击场景地面。
目标直接进入原任务流程，坐标复制和原有选点规则保持不变。
总开关未开、已有任务等情况仍由mission_manager处理；放箱子功能不要求开启导航总开关。

## 动态箱子页

1. 设置长X/宽Y/高Z，单位米，默认各0.4；允许0.1～2。尺寸在放置前设置，要改已存在箱子的尺寸需移除重放。
2. 设置速度，单位m/s，默认0.15，允许0.05～0.5。调整速度输入框会使控制区失焦停车，改完重新启用。
3. 点击“点击地面放箱子”，再点击空旷地面。点击货架顶部不接受；请勿与机器狗或货架重叠。
4. 等“箱子已确认”后点击“启用箱子控制（WASD）”，绿色区域获得键盘焦点。
5. 按住W/S沿世界+X/-X移动，A/D沿世界+Y/-Y移动。也可按住面板方向按钮。松开停车，斜向不叠加超速。
6. 空格/Esc或“停止”会停车并退出箱子控制；再次启用才能移动。停止的只是箱子，机器狗导航不因此取消。
7. “移除箱子”仅移除本面板创建的箱子；等待场景确认后可重新放置。“检查状态”用于外部删除、世界重置或服务超时后的核实。

方向按世界坐标，不是屏幕方向，也不是机器狗朝向。切换页签、点击场景/其他输入框使控制区失焦、
窗口非活动或关闭面板都会停车。用户返回Gazebo后需再次启用控制，不自动恢复旧按键。
关闭面板不会删除箱子，只停车。新面板有新UUID，不接管旧箱子；旧箱子可在Gazebo实体树选中后删除。
每个面板一次管理一个箱子；原普通几何工具及终端moving_obstacle生成的箱子不受本面板控制。

## 推荐测试流程

选择开阔通道，原导航目标页发一个较远目标；切到箱子页，在路线侧面放一个40cm箱子。
开启箱子控制，按住方向键让它低速横穿，观察雷达、costmap、机器狗避让和最终任务结果。
不要直接把箱子生成在机器狗身上，也不要靠拖动瞬移物体冒充连续速度运动。
移除箱子后，雷达重新确认空闲才能清掉旧占据；只有路线改善达到阈值才会后台更新。
面板控制功能通过不等于所有动态避障场景通过；现有RL跟踪/受阻恢复限制仍然存在。

## 实现与接口

同一个GUI插件增加页签，不增加ROS2节点。场景操作通过Gazebo Transport：

| 接口 | 类型/作用 |
|---|---|
| /lite3/selected_goal | 原gz.msgs.Pose导航选点；原ROS桥接保持 |
| /world/large_warehouse/create | gz.msgs.EntityFactory → Boolean，创建专属模型 |
| /world/large_warehouse/remove | gz.msgs.Entity → Boolean，按专属名字移除 |
| /world/large_warehouse/scene/info | Empty → Scene，确认模型实际存在或已移除 |
| /lite3/gui_box/<UUID模型名>/cmd_vel | gz.msgs.Twist，世界轴箱子指令，GUI约20Hz；非机器狗ROS速度话题 |
| 上述cmd_vel/actuator | 内部箱体轴速度，由BoxCommandGuard发给原生VelocityControl；日常不直接操作 |
| 上述cmd_vel/pose、/contacts | gz.msgs.Pose/Contacts，模型实际位姿和碰撞，便于隔离验证 |

UUID模型名以lite3_gui_box_开头。模型包含实际箱体几何、碰撞和按尺寸计算的惯性。
服务器保护约300ms没有新输入则停车，仍取决于仿真执行；暂停时不移动，不是现实机器人安全控制器。
创建/移除的Boolean只代表命令排队，本插件额外查询scene；8秒确认超时禁用控制，要求检查状态。
不从地图真值直接给导航添加障碍，障碍仍须由真实仿真雷达进入原感知/costmap链路。

## 验证

BUILD_TESTING=ON时提供target_picker_interaction和picker_box_physics两项测试。
前者加载真实QML并模拟场景服务/按键；后者启动专属GZ分区的无GUI物理世界，创建真实箱体。
测试不加载机器人或RL，不向用户场景发导航目标。完整记录见development_history/evidence/dual_picker_2026-10-18。

```bash
ctest --test-dir /home/ma/lite3_ws/build/lite3_gazebo -R 'target_picker_interaction|picker_box_physics' --output-on-failure
```
