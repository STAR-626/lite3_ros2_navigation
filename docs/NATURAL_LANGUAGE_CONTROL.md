# 自然语言交互入口：规则模式第一版

2026-10-20当前：bringup的DeepSeek入口默认原生工具闭环，支持环境查询、多物体串行接近和真实结果反馈；不再限制一句话一个物体。旧JSON入口可用agent_tools=false回退，原rules/非AI入口保留。临时接近的固定物体/几何限制仍在；真实API及机器狗实走待验收。见[工具模式说明](AI_TOOL_AGENT.md)。以下单动作/不支持多物体描述是前阶段记录。

本版不调用云端API，也没有下载本地大模型。先把指令、地点和任务执行协议跑通；未来模型只输出相同的白名单动作与参数，再复用校验和执行。没有任意shell命令入口。

## 启动：两个终端

本轮已构建。若旧完整系统还在运行，先在旧bringup终端按Ctrl+C退出。

终端1：

```bash
source /opt/ros/jazzy/setup.bash
source /home/ma/lite3_ws/install/setup.bash
ros2 launch lite3_navigation bringup.launch.py ai_control:=true
```

原仿真、RL、规划控制准备到READY之后，再启动任务节点和交互后台。终端2：

```bash
source /opt/ros/jazzy/setup.bash
source /home/ma/lite3_ws/install/setup.bash
ros2 run lite3_navigation ai_console
```

看到“已连接”后直接输入中文，不要在这些中文前加ros2。原bringup默认`ai_control:=false`，不影响既有操作。后台没开启时，console约8秒内给出未连接提示，不另启动机器人。

## 第一版支持的表达

规则模式请使用以下句式；不是任意措辞都能理解。中文数字支持基本整数和小数，也支持阿拉伯数字、全角数字。

| 输入例子 | 行为 |
|---|---|
| 帮助 | 列出支持的表达 |
| 开启导航 | 调用现有总开关服务；不自动创建移动任务 |
| 停止 / 停下 / 关闭导航 / 取消这次导航 | 取消当前导航、清空剩余队列、关闭入口并请求停止锁定 |
| 查询状态 / 现在是什么状态 | 查询现有任务节点，附加队列数量及标记传输错误 |
| 把坐标3、2，朝向90度设成点1 | 保存地点；坐标为map米，角度为度 |
| 把当前位置设成点2 | 读取新鲜的map→base_footprint位置和朝向并保存 |
| 点1在哪里 / 查询点1 | 查询保存的坐标 |
| 列出地点 / 有哪些已保存的点 | 列出命名地点与本次原点 |
| 删除点1 | 删除文件中的地点并移除其标记 |
| 确认覆盖点1 | 对最近60秒内同名地点的覆盖提议作确认 |
| 去点1 | 查找地点后提交原NavigateTask |
| 去坐标3、2，朝向90度 | 提交坐标导航 |
| 回到原点 / 回家 | 使用本次仿真记录的初始有效位置，不是地图(0,0) |
| 先去点1，再去点2，然后再回到原点 | 顺序执行；前一步成功才发下一步 |
| exit / 退出 / Ctrl+C | 退出交互终端；请求清队列、关闭导航并等待停止响应 |

示例坐标只说明语法；请换成当前地图中有足够身体和朝向空间的目标。导航关闭时地点设置、查询、删除仍可使用，移动请求会被拒绝。

未写朝向时，使用该次保存/整组任务提交时的当前朝向；不会隐式填成0。整组任务在开始前固定所有坐标，执行途中改点只影响下次任务。点名需精确一致，“点一”和“点1”目前是两个名称；后续接模型时可增加别名规范。

## 地点与原点

- 命名地点默认文件：`/home/ma/.local/share/lite3_navigation/places.json`，原子替换保存，重启保留；最多64个。
- 点名1～24字符，允许中文、字母、数字、下划线、短横线；不允许终端命令片段。“原点/初始位置/家”及“那里”等歧义词为保留名称。
- 同名设置不会立刻覆盖；终端展示新坐标，输入“确认覆盖点名”后才保存。确认会话专属，60秒过期，停止或断线会清除。
- 原点属于本次仿真：后台获得第一条新鲜有效位置后自动记录，不从上次文件恢复，不要求每次手动记录。
- 文件包含地图YAML与图片的内容指纹。不同地图/损坏文件会明确报错，不自动覆盖；可使用独立文件启动：

```bash
ros2 launch lite3_navigation bringup.launch.py ai_control:=true places_file:=/home/ma/lite3_places_warehouse.json
```

地点格式合法不等于导航可达。此处先检查动作、有限数字、朝向范围、地点存在性；当前开关/忙碌/故障由任务状态检查，目标轮廓与路线可行性继续由现有任务节点和Nav2负责。队列后面的点不提前保证一定可达。

## Gazebo显示

每个地点显示绿色圆环、点名轮廓和朝向箭头，原点也显示。新建/修改/删除后排队更新，并每3实际秒重发当前标记，以支持GUI晚启动。

本项目现有map与Gazebo world对齐，标记按这套对齐关系绘制；未来接入SLAM后需重新处理地图到仿真世界的转换。

只使用`/marker` GUI标记，不创建Gazebo模型、碰撞体或传感器可见物体。Ogre2当前不支持原生TEXT Marker，因此辅助程序用Qt字体把中文点名转换成LINE_LIST字形轮廓。标签平行于地面，俯视最容易看清，不是自动面向相机的悬浮文字。字体使用系统Noto Sans CJK SC及Qt回退，迁移电脑需要可用中文字体。

“已排队”表示后台发送了显示请求，不冒充图形端已渲染确认。`gui:=false`时没有图形标记显示，不影响地点保存与导航；稍后打开同分区GUI会收到周期重发。

关闭console不删除地点标记；删除地点才删除其圆环/标签/箭头。整个Gazebo关闭后重新启动，后台从地点文件恢复标记。本版未提供拖动标记反向改坐标。

## 通信与执行流程

```text
ai_console（终端节点）
  → /lite3/interaction/input，std_msgs/msg/String，JSON
lite3_interaction（后台节点）
  → 规则解析、地点文件、参数检查
  → /lite3/get_navigation_state，Trigger
  → /lite3/set_navigation_enabled，SetBool
  → /navigate_task，lite3_interfaces/action/NavigateTask
mission_manager → 原Nav2规划控制 → 原运动节点 → RL → Gazebo
  ← Action反馈/结果
  → /lite3/interaction/events，String JSON → console显示

后台 → 非ROS辅助进程place_marker_transport → Gazebo Transport /marker → GUI
```

新增1个常驻后台节点，console打开时另有1个临时ROS节点；标记辅助进程不是ROS节点。没有新增接口包、消息类型或控制器，也没有改RL/现有任务接口。两条交互topic用JSON信封包含session、请求id和类型；重复请求id不执行第二次。它们是本机受信ROS环境协议，不提供网络身份认证，不应直接暴露给外网。

后台只接受单个交互会话，每约0.4实际秒心跳；超过2.5实际秒未收到心跳会清空队列并持续请求关闭导航。心跳与超时使用实际时间，仿真暂停也会检查。退出时最多等待8秒的停止确认；未确认会提示检查bringup，不把请求发送等同于已停止。后台退出由bringup监控并关闭本次整套启动。

每个目标都使用Action成功状态和result_code=0才进入下一步；非成功、拒绝、接口超时、开关关闭都会停止或取消后续步骤。不会按固定sleep猜测到达，不自动重新开启总开关。停止期间迟到的目标接受响应会被取消，不能复活旧队列。

当前任务期间可查询状态和管理地点，但不接受新的导航队列或重新开启；原Gazebo入口仍在，若在任务交接间隙接受了其他来源目标，后续步骤会因忙碌而拒绝，不抢占它。

## 验证边界

已构建并提供以下回归：规则/存储单元测试；真实交互后台+模拟任务服务/Action的顺序、失败、停止、失联、覆盖及终端输入测试；独立Gazebo GUI MarkerManager+真实GPU雷达的显示登记、字形兼容、删除、无模型/无额外雷达命中检查。

这些测试未启动机器狗或RL。本版完整bringup、具体地图目标的实际走完队列仍需要用户实测。原障碍记录稳定性修复和导航已知限制继续有效，不因增加交互而消失。

开发复现先关闭完整系统并加载ROS与工作空间环境：

```bash
python3 -m unittest discover -s /home/ma/lite3_ws/src/lite3_navigation/test -p test_interaction_core.py -v
ROS_DOMAIN_ID=218 GZ_PARTITION=lite3_interaction_20261020 python3 /home/ma/lite3_ws/src/lite3_navigation/test/check_interaction_backend.py
ROS_DOMAIN_ID=219 GZ_PARTITION=lite3_markers_20261020 python3 /home/ma/lite3_ws/src/lite3_navigation/test/check_place_markers.py
```

最后一项会短暂打开独立Gazebo GUI窗口，结束后关闭自己的进程；测试地点仅写入临时目录。正式地点文件不上传Git，分享项目时按需要单独分享。
