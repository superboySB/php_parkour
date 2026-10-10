# SDK0.1.8 隔离试跑：两次启动失败与依赖集合修复

2026-10-10，本轮两次尝试均失败，不能据此宣称 SDK/DDS 退出修复通过。

- `0845`：Docker 在只读 `/data` 下创建 `/data/cache` 挂载点失败，未启动 native executor。容器已停止；修复是在下次独立快照中预建空挂载目录。
- `0850`：进入候选镜像后，首例 simulator 在加载 metadata entrypoint 时遇到 `ModuleNotFoundError: holosoma.bridge.unitree`。未完成 DDS 初始化、策略 rollout 或 SDK 析构验证；其余四例未运行。进程组收据和已停止容器的 inspect 均保留。原始 `native_started=true` 仅表示尝试了 executor，不能解释为 DDS/策略已工作。

旧629计划的340项是当时保存的依赖集合，遗漏了动态选择的 Unitree bridge 与部分父包初始化文件，不能称为完整 Python import closure。旧集合及历史运行源码字节保持不变。当前新计划保守纳入全部 bridge Python 文件，递归加入父包 `__init__.py` 并继续分析其静态 imports；新集合376项，两项新增回归合计78项CPU测试通过。源码及集合见 `dynamic-bridge-closure/`。静态依赖分析不能证明任意动态导入完整，下一次运行仍须先实际导入所选入口。

`observer-host-proc-preflight/` 只证明现有本地容器 init 的 host `/proc`、精确 cgroup 与 NSpid 可读，不证明新的隔离容器或 native `command_writer` 映射通过。正式训练容器、原本地容器与原镜像均未被替换。

本目录为原字节副本，`evidence-manifest.json` 记录来源和SHA；完整输入/冻结源码快照仍保存在本地忽略的 `outputs/research/sdk018-native-pilot-20261010T0845/` 与 `0850/`，不把全部大资产重复提交。
