# 外部 RL 部署成果保存与恢复

这里只保存本项目实际使用的策略、三份修改后的源码快照、可重放补丁、版本和许可。
没有复制整个第三方仓库，也没有复制 build、虚拟环境、二进制依赖库或日志。
原工作目录 `/home/ma/Lite3_rl_deploy` 不受本次同步影响。

## 内容

- `UPSTREAM.json`：准确上游 commit、模型子模块版本、构建选项和 SHA-256。
- `policy/ppo/policy.onnx`：本机已验证的原始预训练策略（758441 字节）。
- `snapshots/`：完整保留三份本地修改文件；不是独立可编译项目。
- `patches/local-simulation-fixes.patch`：相对指定上游版本的修改，可用 git apply 恢复。
- `requirements-mujoco.txt`：可选 MuJoCo 验证环境的实际 Python 依赖版本。
- `LICENSE.DeepRoboticsLab.txt`：原始 BSD 3-Clause 许可，版权 2025 DeepRoboticsLab。

三处修改是：空格将三个运动速度要求归零；进入 ONNX 策略时初始化上一轮动作；
先初始化策略再启动推理线程，避免初始化顺序导致的无效输出。
这些修复没有改变项目的整体规划，也不代表解决了全部线程安全或地形通行问题。

## 全新机器恢复（目录尚不存在时）

先 clone 本项目到 `/home/ma/lite3_ws`。另行获取第三方项目并锁定版本：

```bash
git clone https://github.com/DeepRoboticsLab/Lite3_rl_deploy.git /home/ma/Lite3_rl_deploy
git -C /home/ma/Lite3_rl_deploy checkout --detach 1c4a8f14c9c531903fa5a26783e3f9b99d1039d9
git -C /home/ma/Lite3_rl_deploy submodule update --init -- third_party/deep_robotics_model
git -C /home/ma/Lite3_rl_deploy/third_party/deep_robotics_model checkout --detach b452a1f404d37155400242f18e454fed8bcc51b8
git -C /home/ma/Lite3_rl_deploy apply --check /home/ma/lite3_ws/external/lite3_rl_deploy/patches/local-simulation-fixes.patch
git -C /home/ma/Lite3_rl_deploy apply /home/ma/lite3_ws/external/lite3_rl_deploy/patches/local-simulation-fixes.patch
```

以上 checkout/apply 仅用于全新获取的外部仓库；现有仓库已修改时先检查状态，不重复应用。
本机曾遇到递归初始化时 SDK 内部 URDF 子模块缺少 `.gitmodules` 映射；
当前构建不依赖该内部子模块，因此只明确初始化官方模型子模块，不使用递归初始化。

确认策略与本次保存的一致：

```bash
sha256sum /home/ma/Lite3_rl_deploy/policy/ppo/policy.onnx
sha256sum /home/ma/lite3_ws/external/lite3_rl_deploy/policy/ppo/policy.onnx
```

两者预期均为 `efa6581d314d8c0442881453d39fc082c09b28bbaa3029d328fcd61fa25b57c7`。
指定 commit 已包含该策略，无需重新训练或转换。

### C++ 策略程序构建

```bash
sudo apt update
sudo apt install build-essential cmake libdw-dev libbackward-cpp-dev
cmake -S /home/ma/Lite3_rl_deploy -B /home/ma/Lite3_rl_deploy/build -DBUILD_PLATFORM=x86 -DBUILD_SIM=ON -DSEND_REMOTE=OFF
cmake --build /home/ma/Lite3_rl_deploy/build -j4
```

上游已包含 x86 ONNX Runtime 与当前 C++ 构建所需依赖。
`BUILD_SIM=ON` 使用官方的 UDP 仿真接口；虽有 `USE_PYBULLET` 宏，当前 Gazebo
联调不需要同时启动 PyBullet 或 MuJoCo。
本次补丁恢复检查在上游原始文件副本中通过；全新电脑完整安装与 GUI 启动仍需实测。

### 可选：单独恢复 MuJoCo 验证环境

Gazebo 运行不需要这一步；仅用于复现先前的独立 MuJoCo 策略测试。

```bash
sudo apt install python3-venv
python3 -m venv /home/ma/Lite3_rl_deploy/.venv
/home/ma/Lite3_rl_deploy/.venv/bin/python -m pip install -r /home/ma/lite3_ws/external/lite3_rl_deploy/requirements-mujoco.txt
cd /home/ma/Lite3_rl_deploy/interface/robot/simulation
/home/ma/Lite3_rl_deploy/.venv/bin/python mujoco_simulation.py
```

另一个终端从 `/home/ma/Lite3_rl_deploy/build` 执行 `./rl_deploy`。
不要同时启动 Gazebo 控制插件和 MuJoCo；两者都需要本机 UDP 20001 端口。

## 来源和许可

Lite3 pretrained policy and deployment source originate from DeepRobotics / DeepRoboticsLab.
上游根目录为 BSD 3-Clause；本机检查未发现该权重另附独立许可说明。
保留完整版权、许可条件和免责声明。本项目仓库保持 private；将来公开之前应再次
核查模型权重是否有补充使用条件。独立第三方依赖仍遵循各自许可证，不随本目录整体转载。
