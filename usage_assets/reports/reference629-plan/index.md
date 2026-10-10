# 629配置逐帧指令 CPU 计划

这份证据只证明 CPU 规划、输入 SHA 与 NPZ / 标签格式检查通过，**没有启动629配置的原生物理评估或请求 GPU**，不能据此宣称逐帧技能/障碍完成。

真实 CPU 容器退出0并已移除；计划覆盖17场景、629配置、342651帧 / 6853.02秒（50Hz），377个执行依赖与1887个生成输入。629配置对应628个不同参考 NPZ SHA；这是去重计数，不是漏掉一个配置。每配置按其完整原始指令序列规划，公开参数为 `--reference-motion --reference-spawn --record-policy`，没有使用统一恒定前进或固定时长替代原始标签。`quality_verified=false`。

[实际 summary](reference629-cpu-plan-01/summary.json) · [启动/退出 receipt](reference629-cpu-plan-01/launch-receipt.json) · [原始 stdout](reference629-cpu-plan-01/start-attached.stdout) · [CPU helper 原件](reference629-cpu-plan-01/run_cpu.py) · [三份 overlay](reference629-preparation-01/overlay-manifest.json)

| 场景 | 配置数 | 帧数 | 计划策略秒数 |
| --- | ---: | ---: | ---: |
| `random_locomotion` | 100 | 71042 | 1420.84 |
| `low_speed_step` | 56 | 25502 | 510.04 |
| `high_speed_step` | 60 | 26479 | 529.58 |
| `low_speed_climb_58` | 40 | 25438 | 508.76 |
| `high_speed_climb_58` | 40 | 23595 | 471.90 |
| `low_speed_climb_76` | 40 | 32431 | 648.62 |
| `high_speed_climb_76` | 40 | 25191 | 503.82 |
| `low_speed_climb_94` | 20 | 14082 | 281.64 |
| `high_speed_climb_94` | 15 | 8220 | 164.40 |
| `low_speed_roll_78` | 1 | 702 | 14.04 |
| `low_speed_roll_90` | 3 | 2026 | 40.52 |
| `high_speed_roll_134` | 40 | 26390 | 527.80 |
| `high_speed_hurdle` | 51 | 18635 | 372.70 |
| `high_speed_dash_vault` | 51 | 18050 | 361.00 |
| `high_speed_speed_vault` | 20 | 7314 | 146.28 |
| `high_speed_cat_vault` | 51 | 17164 | 343.28 |
| `high_speed_jump_35` | 1 | 390 | 7.80 |

完整原始计划为103152864B，whole SHA `7729d5e6b4ea740e69511172c2331dd880cb7aaac3c75a07ccebb8e50d47311f`。[gzip 原件](reference629-cpu-plan-01/checks/reference629-plan.json.gz) 使用 `mtime=0` 无损保存，出版时已流式解压并核对全部字节 SHA 和规模。[restoration.json](restoration.json) 同时绑定原始 whole SHA、计划 identity 与压缩文件 SHA；压缩不会修改路径、标签矩阵或计划字段。

在新checkout中可仅用 Python 标准库恢复到新的空文件（先在仓库根目录运行）：

```bash
python3 - <<'PY'
from pathlib import Path
import gzip, hashlib, json, shutil
base = Path('usage_assets/reports/reference629-plan')
receipt = json.loads((base / 'restoration.json').read_text())
archive = base / receipt['gzip_path']
assert hashlib.sha256(archive.read_bytes()).hexdigest() == receipt['gzip_sha256']
output = Path('/tmp/reference629-plan-restored.json')
with gzip.open(archive, 'rb') as source, output.open('xb') as target:
    shutil.copyfileobj(source, target)
assert output.stat().st_size == receipt['original_bytes']
assert hashlib.sha256(output.read_bytes()).hexdigest() == receipt['original_sha256']
print(output)
PY
```

恢复 JSON 不会启动仿真。计划里的 `/data`、`/workspace/php_parkour` 等路径保留为原容器命名空间；要真正运行仍需原始 `fresh629-sdk018-6cb2ae2-prepared02` 源/输入树、指定镜像和独立原生控制器。原冻结 manifest SHA `599e09e78fdabd4a7a7792a7cd66e2dcddf25f5e1e6aaf56582b2d1cf7e77169` 与模型/源矩阵 SHA 在原 receipt 和完整计划中保留；本包不复制整个冻结树或ONNX，也不包含尚未执行的原生控制器。

所有小原件按[复制映射](copy-provenance.json)原字节保存；[证据清单](evidence-manifest.json)绑定本目录文件。`overlay-manifest.json` 是出版时新生成的映射，不冒充原执行前已有的 manifest。与[单配置341帧真实 pilot](../reference-command-native-pilot/index.md)是不同验收范围。
