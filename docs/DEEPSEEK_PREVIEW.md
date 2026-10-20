# DeepSeek 接入第一步：本机密钥与独立解析预览（2026-10-20）

当前阶段只增加三个独立Python工具，不接ROS，不发送任务，不替换正在运行的规则后台。使用Python标准库，无需pip安装。模型尚未实际在线验证；离线16项校验/模拟HTTP/密钥错误脱敏检查通过，不等于真实API调用成功。

## 用户在空闲终端操作

```bash
python3 /home/ma/lite3_ws/src/lite3_navigation/scripts/deepseek_setup.py
```

看到提示后粘贴DeepSeek API Key并回车，输入不回显。工具不会联网，只以600权限原子保存到`/home/ma/.config/lite3_navigation/deepseek.json`。该文件在Git仓库外，不要复制进仓库、截图或发到聊天。已有文件需本机确认更新；不要使用sudo运行。

然后启动独立预览：

```bash
python3 /home/ma/lite3_ws/src/lite3_navigation/scripts/deepseek_preview.py
```

这里直接输入自由表达，例如“麻烦先到点1，再去点2，最后回家”。每条输入把这句话、已有地点名称及待澄清短对话发送到DeepSeek，会使用API额度；不发送密钥文件内容、工程文件、地图图片、点云或完整地点坐标表；你在原话里输入的坐标会随这句话和澄清历史发送。认证头只用于DeepSeek HTTPS端点。

结果只显示动作JSON与必要的本地检查提示，不执行导航。明确的规则停止语句本地识别、不调用API；因为是独立预览，也不会真的停止正在运行的机器人。实际停车仍用原ai_console中的“停止”或现有项目停止入口。输入exit/quit/退出或Ctrl+C关闭预览。

已保存地点名称从现有places.json读取，单次请求只携带最近3轮、90秒内的待澄清原话与问题；可以直接补充回答，完成动作或停止后清空，不保存完整聊天。省略角度输出null，等未来执行层读取当前朝向；不让模型猜坐标。JSON格式正确仍须通过本机白名单/字段/数值检查。

## 接口配置与来源

- 固定认证目标：`https://api.deepseek.com/chat/completions`；拒绝HTTP重定向，避免把认证转发到其他站点。
- 本次按官方文档使用模型名`deepseek-flash`，`thinking.type=disabled`，JSON Output，最多1500输出token，25秒网络操作超时。
- JSON Output要求提示中包含json及输出示例，响应也可能为空；程序拒绝空内容、截断、非法字段、重复键和非有限数字。
- 不输出HTTP错误正文或认证头，错误只显示状态码及通用原因。未自动重试，不因失败回退为动作执行。
- 模型和接口可用性、额度以真实调用为准，不承诺耗时或费用。

官方依据（本轮已查看）：[JSON Output](https://api-docs.deepseek.com/guides/json_mode/)和[Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)。

## 后续执行入口

用户已确认实际API预览正常，正式交互入口已增加可选DeepSeek模式，见[执行说明](DEEPSEEK_EXECUTION.md)。本页的独立预览工具仍不连接ROS、不执行动作；不要用预览界面停车。正式模式网络请求与心跳/停止解耦，迟到响应不恢复已取消任务。
