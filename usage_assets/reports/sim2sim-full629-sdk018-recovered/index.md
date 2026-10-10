# recovered629真实物理结果

[629配置离线画廊](playback.html) · [四例独立补验](supplement.html) · [机器汇总](summary.json) · [公共gate真实返回](gate-admission.json) · [全部proof路径映射](proof-path-map.json)

实际633次attempt，覆盖629个唯一配置。原629/1258worker/629全片decode的CPU证明与原1250host映射保留；speed-vault cfg0004–0007的八个旧映射仍明确缺失，另四次新attempt提供八个独立新映射、四段全片decode。原host退出143不改写为0，不声称原连续1258映射。所有阈值事件保留，quality_verified=false。

本画廊的629主结果始终显示原629结果，不挑选四例补验覆盖原结果。每场景固定原config0的17个代表视频如下。

- [random_locomotion](raw/original/random_locomotion/config-0000/attempt-0001/video/episode_0_1791626566.mp4) · [PNG](raw/original/random_locomotion/config-0000/attempt-0001/video/episode_0_1791626566.png)
- [low_speed_step](raw/original/low_speed_step/config-0000/attempt-0001/video/episode_0_1791628763.mp4) · [PNG](raw/original/low_speed_step/config-0000/attempt-0001/video/episode_0_1791628763.png)
- [high_speed_step](raw/original/high_speed_step/config-0000/attempt-0001/video/episode_0_1791629991.mp4) · [PNG](raw/original/high_speed_step/config-0000/attempt-0001/video/episode_0_1791629991.png)
- [low_speed_climb_58](raw/original/low_speed_climb_58/config-0000/attempt-0001/video/episode_0_1791631307.mp4) · [PNG](raw/original/low_speed_climb_58/config-0000/attempt-0001/video/episode_0_1791631307.png)
- [high_speed_climb_58](raw/original/high_speed_climb_58/config-0000/attempt-0001/video/episode_0_1791632186.mp4) · [PNG](raw/original/high_speed_climb_58/config-0000/attempt-0001/video/episode_0_1791632186.png)
- [low_speed_climb_76](raw/original/low_speed_climb_76/config-0000/attempt-0001/video/episode_0_1791633063.mp4) · [PNG](raw/original/low_speed_climb_76/config-0000/attempt-0001/video/episode_0_1791633063.png)
- [high_speed_climb_76](raw/original/high_speed_climb_76/config-0000/attempt-0001/video/episode_0_1791633942.mp4) · [PNG](raw/original/high_speed_climb_76/config-0000/attempt-0001/video/episode_0_1791633942.png)
- [low_speed_climb_94](raw/original/low_speed_climb_94/config-0000/attempt-0001/video/episode_0_1791634824.mp4) · [PNG](raw/original/low_speed_climb_94/config-0000/attempt-0001/video/episode_0_1791634824.png)
- [high_speed_climb_94](raw/original/high_speed_climb_94/config-0000/attempt-0001/video/episode_0_1791635264.mp4) · [PNG](raw/original/high_speed_climb_94/config-0000/attempt-0001/video/episode_0_1791635264.png)
- [low_speed_roll_78](raw/original/low_speed_roll_78/config-0000/attempt-0001/video/episode_0_1791635592.mp4) · [PNG](raw/original/low_speed_roll_78/config-0000/attempt-0001/video/episode_0_1791635592.png)
- [low_speed_roll_90](raw/original/low_speed_roll_90/config-0000/attempt-0001/video/episode_0_1791635614.mp4) · [PNG](raw/original/low_speed_roll_90/config-0000/attempt-0001/video/episode_0_1791635614.png)
- [high_speed_roll_134](raw/original/high_speed_roll_134/config-0000/attempt-0001/video/episode_0_1791635681.mp4) · [PNG](raw/original/high_speed_roll_134/config-0000/attempt-0001/video/episode_0_1791635681.png)
- [high_speed_hurdle](raw/original/high_speed_hurdle/config-0000/attempt-0001/video/episode_0_1791636563.mp4) · [PNG](raw/original/high_speed_hurdle/config-0000/attempt-0001/video/episode_0_1791636563.png)
- [high_speed_dash_vault](raw/original/high_speed_dash_vault/config-0000/attempt-0001/video/episode_0_1791637681.mp4) · [PNG](raw/original/high_speed_dash_vault/config-0000/attempt-0001/video/episode_0_1791637681.png)
- [high_speed_speed_vault](raw/original/high_speed_speed_vault/config-0000/attempt-0001/video/episode_0_1791638798.mp4) · [PNG](raw/original/high_speed_speed_vault/config-0000/attempt-0001/video/episode_0_1791638798.png)
- [high_speed_cat_vault](raw/original/high_speed_cat_vault/config-0000/attempt-0001/video/episode_0_1791639237.mp4) · [PNG](raw/original/high_speed_cat_vault/config-0000/attempt-0001/video/episode_0_1791639237.png)
- [high_speed_jump_35](raw/original/high_speed_jump_35/config-0000/attempt-0001/video/episode_0_1791640355.mp4) · [PNG](raw/original/high_speed_jump_35/config-0000/attempt-0001/video/episode_0_1791640355.png)

原始结果、worker收据、sealed reports、控制源码和完整observer流均以原字节收入本发布。超过25MB或observer JSONL按连续不超过25,000,000B分块，.chunks.json保留whole bytes/SHA和顺序；拼接后须核whole SHA。原始JSON保留历史绝对路径，proof-path-map.json给出其实际发布副本或分块位置。

evidence_publication_self_contained=true仅指验收raw证据闭包。[reproduction-inputs-external.json](reproduction-inputs-external.json)明确保留5206冻结树/大模型/生成几何的外部恢复前提和精确SHA；本包不声称独立还原原机器GB级树。恢复原始输入应使用仓库note.md/usage.md、官方release资产与原plan/freeze SHA逐文件核验。
