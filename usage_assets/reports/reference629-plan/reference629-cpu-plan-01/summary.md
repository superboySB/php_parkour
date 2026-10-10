# 真实 CPU reference629 计划

唯一独立 runc / network none / GPU hidden 容器已真实退出 0 并删除；未运行原生仿真或策略。

计划包含 17 场景、629 配置、342651 帧（50 FPS）、6853.02 policy 秒。377 个依赖，1887 个输入路径；628 个不同 NPZ SHA。

完整计划为 103,152,864 B，SHA `7729d5e6b4ea740e69511172c2331dd880cb7aaac3c75a07ccebb8e50d47311f`；内部身份 `9fad5096d831d5c83d26f126f36a6b30d1e8d3b57b802678c5cf6f4915b7455e`。3.091 秒为 docker start -a 的真实墙钟时间。未采样容器峰值内存，因此报告为 null。

| 场景 | 配置 | 帧 | policy 秒 |
|---|---:|---:|---:|
| random_locomotion | 100 | 71042 | 1420.84 |
| low_speed_step | 56 | 25502 | 510.04 |
| high_speed_step | 60 | 26479 | 529.58 |
| low_speed_climb_58 | 40 | 25438 | 508.76 |
| high_speed_climb_58 | 40 | 23595 | 471.90 |
| low_speed_climb_76 | 40 | 32431 | 648.62 |
| high_speed_climb_76 | 40 | 25191 | 503.82 |
| low_speed_climb_94 | 20 | 14082 | 281.64 |
| high_speed_climb_94 | 15 | 8220 | 164.40 |
| low_speed_roll_78 | 1 | 702 | 14.04 |
| low_speed_roll_90 | 3 | 2026 | 40.52 |
| high_speed_roll_134 | 40 | 26390 | 527.80 |
| high_speed_hurdle | 51 | 18635 | 372.70 |
| high_speed_dash_vault | 51 | 18050 | 361.00 |
| high_speed_speed_vault | 20 | 7314 | 146.28 |
| high_speed_cat_vault | 51 | 17164 | 343.28 |
| high_speed_jump_35 | 1 | 390 | 7.80 |

输入 NPZ 按原样验证，不重采样、不修正标签。全部实际逐帧 onehot、0..11 编码、50 FPS、T/50 时长校验通过；原 matrix 与冻结 overlay3 前后 SHA 一致。

后续 controller 已写入 ../reference629-native-controller-01.py，尚未启动。它从本次 overlay3 原字节复制新 overlay，以旧 frozen source 和 inputs 只读挂载，在共享 UUID 独占锁内重查 GPU idle；新唯一容器内先向 /checks 写 CPU 计划并逐字节比较本次计划，不创建原生输出，再运行原矩阵全629 reference CLI。

原生等待无额外超时、不重试。终态必须 native/observer actual wait 0、629 完整、1258 worker 0/自有组空、每例两条真实 host writer birth 唯一映射；保存全部 raw 并只停止 exact own CID。原生核心保留每例自身 bounded wall timeout。observer 上限 86400 秒。完整 MP4 解码仍须后置 CPU 验证，完成执行也不代表技能/课程成功。

该 controller 只做 AST 静态解析，未导入或执行。Root 审阅后用其真实 parent launcher 启动；当前没有 reference629 物理结果。
