# 六种教师 preset 的实际 CPU 导出检查

六种配置各自的第1轮原生 PT 与自动保存 ONNX 均通过检查，共 **72 个参考查询用例、60 个 PT/ONNX 动作均值对照**，最大绝对误差 `6.333e-8`（阈值 `rtol=1e-5, atol=1e-6`）。六份模型和原阶段 manifest 的 PT SHA 相同；ONNX 内配置/迭代与 PT 一致，权重有限，检查未初始化 CUDA。实际命令和退出码见 [第二次执行回执](teacher-preset-cpu-host/execution-attempt-02.json)，[完整机器结果](teacher-preset-cpu-final-02/summary.json)。

这些是64环境、2迭代的 smoke 模型，不是正式日程结果。检查只证明导出与确定性动作均值、图内参考查询；五个非默认配置的实际 Isaac 重载仍待本地629扫描释放GPU后执行，技能质量没有自动置为通过。

| preset 后缀 | actor / critic 输入 | reference anchor | 动作缩放配置 |
| --- | --- | --- | --- |
| `ref` | 449 / 575 | torso_link | `0.25 × effort_limit / Kp` |
| `no-heightscan` | 160 / 286 | torso_link | 同上 |
| `ref-noscale` | 449 / 575 | torso_link | 1.0 |
| `no-heightscan-noscale` | 160 / 286 | torso_link | 1.0 |
| `ref-pelvis` | 449 / 575 | pelvis | `0.25 × effort_limit / Kp` |
| `no-heightscan-pelvis` | 160 / 286 | pelvis | 同上 |

这里检查保存的缩放配置，没有运行物理动作缩放实验。均值对照忠实于本次无normalizer、无dropout的四层Linear/ELU原生actor；PPO的std不参与确定性mean。参考检查比较图内表的0/1/中间/末帧/上界截断/小数索引，未独立重建整套源参考，也未检查负时间。[独立源码与实际PT复核](teacher-preset-independent-review/review.md)。

原始YAML和PT配置的直接相等比较为false，诊断原样保留：六份各仅一处 `actor.output_dim[0]` 从保存时的字符串 `robot_action_dim`，被原生setup解析为PT中的整数29。其它字段无差异；这不是已证的重载故障，也没有改写YAML来制造相等。[精确差异与原生保存顺序](teacher-preset-independent-review/yaml-vs-pt-diff.md)。

新增8项配置错配拒绝测试通过；与完整场景发布工具24项合并的根验证为32/32，独立8项是重复复核，不额外计数。初次较窄检查同样72/60通过，其源码、回执和结果另存`*-01`；第二次加入缩放身份门卫后仍通过，未累加两次样本。

复跑已有 smoke 输出：

```bash
docker exec -e CUDA_VISIBLE_DEVICES= -e OMP_NUM_THREADS=1 php-parkour-research \
  /opt/php/bin/train-python scripts/research/validate_teacher_presets.py \
  --root /outputs/final-cloud-acceptance/results/smoke \
  --output /outputs/teacher-presets-cpu-new
```

新环境先用`train_pipeline.sh teacher-presets --profile smoke --skills locomotion`生成六份实际模型，再将`--root`指向该输出的`smoke`目录。全部科学依赖在现有Docker内。
