# 完整629物理证据发布工具：开发验收

本轮仅新增离线发布工具及CPU测试，没有运行仿真、改变340项冻结依赖、17代表场景gallery或原始运行证据。当前完整发布被实际门卫拒绝（exit2）；无完整629完成声明。

- 新增 `scripts/research/publish_full_scene_matrix.py`：固定plan identity、终态driver exit0/完整629 matrix SHA、每例500ticks/10s/gantryoff、340依赖与1887源输入、sealed历史attempt和原始媒体SHA完整性门卫。历史unsealed失败保留原字节与当前指纹，明确不冒充封存验收。
- 输出逐配置CSV/JSON、17场景汇总、原始plan/matrix/driver回执/全部attempt日志结果和视频截图、完整SHA manifest与离线playback.html。24项分页且preload=none；世界XY SVG直接绘制实际policy轨迹，不平滑。629是配置数，不是629种独立几何或技能成功。
- `tests/test_publish_full_scene_matrix.py`：24/24 CPU回归通过，覆盖运行中/非零退出/部分覆盖/过期hash、来源篡改、499ticks/吊架/模型绑定、视频清单、历史sealed篡改/unsealed保留/未知retry目录、原证据防覆盖。测试内部为明确标记的synthetic fixture。
- 真实预览：`outputs/research/full-scene-publisher-preview-final/playback.html`。只复制实际最前2例，1例阈值事件，coverage=false。原preview保留。49项发布manifest和全部original byte copies通过。
- `scripts/research/verify_full_scene_gallery.py` 使用已有Chrome的CPU软件解码，最多4并发媒体，逐页校验每个video metadata/seek、实际play、PNG/SVG、搜索/场景/阈值筛选。当前只实际验证2例/2MP4/2PNG/2SVG；完整629浏览器检查尚未发生。截图与报告在 `outputs/research/full-scene-publisher-browser-complete/`。
- 完整原媒体预计约0.40GB（155份已封存完成case样本均值外推），另约15–40MB页面/JSON/SVG/manifest；不同场景可能更大，建议预留0.5–1.5GB。此为估计，不是最终字节统计。

完整物理扫描真实完成后，方可使用下列命令；当前同一命令会拒绝完整发布：

```bash
python3 scripts/research/publish_full_scene_matrix.py \
  --plan outputs/research/sim2sim/all-configs-final/plan.json \
  --matrix outputs/research/sim2sim/all-configs-final/matrix.json \
  --driver-receipt outputs/research/sim2sim-all-configs-host/full-driver.json \
  --driver-launch outputs/research/sim2sim-all-configs-host/full-launch.json \
  --driver-wrapper outputs/research/sim2sim-all-configs-host/full_driver.py \
  --output usage_assets/sim2sim/all-configs
python3 scripts/research/verify_full_scene_gallery.py \
  --gallery usage_assets/sim2sim/all-configs/playback.html \
  --output outputs/research/full-scene-gallery-final-browser
```

[机器报告与source SHA](report.json) · [完整发布实际拒绝stderr](full-refusal.stderr.log)
