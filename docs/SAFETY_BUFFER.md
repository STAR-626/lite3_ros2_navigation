# 停止余量与缓冲区：应用和验证

本候选补丁在临时副本编写/编译，不直接改用户项目。应用后需要用户编译、重启和逐项验收。
数值/合成地图验证不是Gazebo/RL验收。所有初值均不是已标定的安全保证。

## 1. 修改范围与目的

- src/lite3_navigation/src/safety_motion.hpp：反应时间、实际速度停止、指令过渡与即时响应预测，25ms步长。
  线速度在世界坐标积分；停止指令不会把实际速度瞬间抹为0。减速能力是暂定模型，不是实测保证。
- avoidance_controller.cpp：保留Rotation Shim/MPPI/RPP结构；在同一安全检查中使用实际速度，
  检查完整保护轮廓边界/内部/未知/地图外；保护带内限制平移速度，再校验修改后的指令。
- 四份planner/controller配置：padding统一0.07。原裸轮廓0.80×0.36米不变，保护外沿从0.84×0.40增至0.94×0.50米。
  青色内切半径由20cm变25cm，规划与执行一致。可能拒绝更窄通道，需要重新选择适合演示的可行路线。
- 默认controller_mppi.yaml增加六个安全参数。旧controller:=rpp入口只共享新的轮廓，不具备本候选完整保护算法。
- 两个回归测试及当前说明文档；没有新增常驻节点、改变RL、修改URDF/STL、取消用户停止或提交Git。

缓冲带与硬碰撞区不同：缓冲带只限速，规划仍依据静态/实测障碍和保护轮廓；
规划的软膨胀代价继续存在。静态地图不能随意清除来让机器狗通行。

## 2. 参数含义（默认MPPI入口）

|controller_server的FollowPath参数|初值|意义|
|---|---:|---|
|safety_reaction_time|0.25|停止/新指令生效前仍按实际速度移动的假定仿真秒数|
|safety_linear_decel|0.5|假定平移减速度m/s²，数值越大，预测停止距离反而越短，不可随意调大|
|safety_angular_decel|2.0|假定转动减速度rad/s²，也需要实际验证|
|safety_lookahead|1.0|新速度指令预测仿真秒数，保留即时响应与有延迟两种检查|
|safety_slow_distance|0.4|距整个导航保护轮廓外沿的缓冲距离，米，不是距机器人中心|
|safety_slow_linear_speed|0.32|缓冲区内平移速度向量长度上限m/s；不会把原本更小的速度提高|

.4m/s、反应.25秒、减速.5m/s²时，模型停止距离约.26m；缓冲带初值.4m给提前限速留出空间。
原RL在过低速度可能不迈步；不把速度无限降到0.05，也不能声称.32在所有组合动作下都可靠。
这些参数在configure时读取：改YAML后须构建并重启，不要仅param set就认为运行算法已改变。
仿真变速、暂停、控制负载变化及动作延迟可能改变实际表现，需要重新验收。

## 3. 用户应用前

先在bringup终端Ctrl+C退出整个系统。补丁必须先git apply --check通过，再git apply。
补丁不会创建commit或push。源码与文档都在补丁范围；应用前备份导航包及相关文档。
如果check报错，停止并保存报错，不使用强制覆盖或reset来应用。

## 4. 编译与数值检查（终端1，系统保持关闭）

```bash
source /opt/ros/jazzy/setup.bash
source /home/ma/lite3_ws/install/setup.bash
cd /home/ma/lite3_ws
colcon build --packages-select lite3_navigation
source /home/ma/lite3_ws/install/setup.bash
g++ -std=c++17 -O2 -Wall -Wextra -Werror /home/ma/lite3_ws/src/lite3_navigation/test/check_safety_motion.cpp -o /tmp/lite3_safety_motion_check
/tmp/lite3_safety_motion_check
```

预期1个包构建完成、14项数值检查通过。遇到错误先停止，不进入运动测试。
这一步没有发送任何ROS速度或导航任务。

## 5. 启动与只读核对

终端1：

```bash
ros2 launch lite3_navigation bringup.launch.py
```

等READY和站稳。终端2：

```bash
source /opt/ros/jazzy/setup.bash
source /home/ma/lite3_ws/install/setup.bash
ros2 param get /controller_server FollowPath.safety_reaction_time
ros2 param get /controller_server FollowPath.safety_slow_distance
ros2 param get /local_costmap/local_costmap footprint_padding
ros2 param get /global_costmap/global_costmap footprint_padding
```

预期依次0.25、0.4、0.07、0.07。RViz不会新增“缓冲带”专用显示；现有膨胀层不变，内切半径增加。
新的日志：Safety buffer表示平移速度已限制；Measured stopping envelope blocked表示
模型认为当前实际运动不能在障碍前停止，控制器拒绝继续输出并沿原有限恢复流程处理；
Command / measured transition envelope blocked表示新动作或实际速度过渡轨迹未通过检查。
单次拒绝不等于任务失败；持续失败仍可能耗尽原5次恢复，不会无限自动解锁/重试。

## 6. 逐项手动验收（终端2）

先开总开关：

```bash
ros2 service call /lite3/set_navigation_enabled std_srvs/srv/SetBool '{data: true}'
```

只在本机默认世界、默认初始位置约(-4,-4)、周围无额外箱子时，先测试：

```bash
ros2 run lite3_navigation navigate -3 -4 0
```

等待RESULT 0并停稳，再测试返回：

```bash
ros2 run lite3_navigation navigate -4 -4 0
```

第二个命令用于检查身后目标是否转身、是否仍长距离后退；本补丁不保证该独立行为问题已解决。
若失败，不连续堆目标；执行下方查询，保存终端输出和RViz/Gazebo录像：

```bash
ros2 service call /lite3/get_navigation_state std_srvs/srv/Trigger '{}'
```

直线与返回通过后，再在Gazebo选一个正常可停靠、与货架留有余量的目标，观察转向是否擦入禁区，
同时记录是否出现限速日志、是否过于保守而无法前进。单次偶然成功不足以用于演示，关键路线至少连续3次成功。
不要选择地图里的障碍内部，或在机器狗仍重叠货架时用这些命令强行测试；先退出重启到默认起点。
关闭入口并停止当前任务：

```bash
ros2 service call /lite3/set_navigation_enabled std_srvs/srv/SetBool '{data: false}'
```

## 7. 动态箱子的自动回归（最后执行）

先在终端1 Ctrl+C退出可见bringup，确认整套系统退出，防止占用同一UDP端口。
在已source的空闲终端执行：

```bash
ROS_DOMAIN_ID=197 GZ_PARTITION=lite3_avoidance_validation_20261017 python3 /home/ma/lite3_ws/src/lite3_navigation/test/check_continuous_avoidance.py --scenario moving --turn
```

这是已有的隔离验收工具：会自动启动另一套无GUI仿真、RL和导航，在空地途中加入横穿箱子并追加转向。
它会实际发送运动任务，但不会连接默认ROS域。不要同时再开bringup/MuJoCo/RL。
成功应有PASS moving和RESULT_FILE；失败保存完整错误及RESULT_FILE，不能据软件编译或数值检查称通过。
真实箱接触需要为0、接触数据有心跳、任务成功、机器人未跌倒。箱接触为0不证明对所有货架绝对安全。
自动测试结束会清理自己启动的进程；回到可见演示仍需正常启动bringup。

人工Teleop横穿是后续补充：只在任务途中、可观察的开阔路段测试，不把箱子生成在机器人身上；
当前未实现任务结束后站着不动时主动躲避被人为推来的物体。

## 8. 交付判定和记录

需要分别记录：直线、后方目标、货架附近转向、移动箱子；每项给出成功/失败、停止位置、结果码、
重规划次数、接触/跌倒和是否过度停车。失败即停止参数加码，保留现场检查地图、实际速度和指令。
当前临时验证只有14项数学与域209合成数据测试，Gazebo/RL实走尚未进行。
无法承诺任意动态环境零碰撞或永不卡住；真实无路应正确停止并返回失败，正常可通行演示路线需反复通过。
Git提交和推送另行进行，本补丁不做。
