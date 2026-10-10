# 最终镜像：17 场景原生 ONNX 闭环实测

镜像 `sha256:88254ac0b90a3056375145601d741aa3e08726e18412d201a3c7e7915a23996f`。每场景固定选 1 个 motion-matching 生成配置的实际 OBJ；低/高速输入为 1/6、seed42、独立 reset、gantry 释放后 500 次策略控制。总墙钟 348.98 秒，17/17 执行完成，0 执行错误。

[全部视频、截图和轨迹](../sim2sim/scenarios/playback.html) · [逐 SHA 完整矩阵](sim2sim-scene-matrix.json)

阈值事件指任意采样时刻 pelvis<0.4 m 或 upright<0.35；部分事件后策略恢复直立，因此事件不是永久倒地计数。14 项触发阈值，3 项未触发。以下数值来自 gantry 关闭后的真实 simulator 世界坐标，up 为身体竖直轴在世界 Z 上的投影。

| 场景 | 指令 | 仿真秒 | 路程 m | 最低 pelvis m | 最低 up | 末态 up | 阈值事件 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| random_locomotion | 6 | 10.014 | 20.481 | 0.620 | 0.854 | 0.984 | 无 |
| low_speed_step | 1 | 10.018 | 3.561 | 0.421 | -0.271 | 0.385 | 有 |
| high_speed_step | 6 | 10.002 | 19.653 | 0.627 | 0.245 | 0.978 | 有 |
| low_speed_climb_58 | 1 | 10.014 | 7.510 | 0.712 | 0.902 | 0.996 | 无 |
| high_speed_climb_58 | 6 | 10.004 | 10.215 | 0.622 | 0.076 | 0.986 | 有 |
| low_speed_climb_76 | 1 | 10.010 | 3.682 | 0.674 | -0.001 | 0.982 | 有 |
| high_speed_climb_76 | 6 | 10.012 | 10.266 | 0.628 | 0.159 | 0.985 | 有 |
| low_speed_climb_94 | 1 | 10.000 | 4.036 | 0.660 | 0.233 | 0.577 | 有 |
| high_speed_climb_94 | 6 | 10.012 | 7.561 | 0.063 | -0.735 | -0.049 | 有 |
| low_speed_roll_78 | 1 | 10.002 | 3.784 | 0.652 | 0.020 | 0.992 | 有 |
| low_speed_roll_90 | 1 | 10.010 | 3.930 | 0.373 | -0.322 | -0.275 | 有 |
| high_speed_roll_134 | 6 | 10.010 | 4.775 | 0.064 | -0.529 | -0.017 | 有 |
| high_speed_hurdle | 6 | 10.008 | 20.420 | 0.626 | 0.880 | 0.986 | 无 |
| high_speed_dash_vault | 6 | 10.014 | 7.881 | 0.066 | -0.643 | 0.020 | 有 |
| high_speed_speed_vault | 6 | 10.006 | 14.147 | 0.609 | 0.091 | 0.983 | 有 |
| high_speed_cat_vault | 6 | 10.018 | 6.233 | 0.063 | -0.998 | -0.018 | 有 |
| high_speed_jump_35 | 6 | 10.012 | 2.070 | 0.548 | 0.201 | 0.223 | 有 |

无事件的 random_locomotion、low_speed_climb_58、high_speed_hurdle 也没有获得障碍完成或技能掌握认证。high_speed_climb_94、low_speed_roll_90、high_speed_roll_134、high_speed_dash_vault、high_speed_cat_vault 末态高度低或朝向异常；完整失败视频均保留。high_speed_jump_35 末态 up=0.223，明显倾斜。

公开训练数据提供 locomotion、低/高速 step、低/高速 climb76 五类 bundle。场景可生成与发布 ONNX 已掌握该技能是不同的事实；本次只验证实际发布模型在各代表几何上的闭环行为。恒定前进指令没有重放参考动作的站立/转向/速度时序；170 秒目标时长不构成 629 配置的策略覆盖。所有结果 `quality_verified=false`、`obstacle_course_completion_verified=false`。

视频包含启动、3 仿真秒 gantry 稳定和退出阶段，所以 MP4 时长大于表中策略控制时长；不能以墙钟或视频总时长代替策略仿真秒。每项具体模型/OBJ SHA、配置名称、指令时间、CSV、MP4/PNG 探针和结果 JSON 可从完整矩阵及视频页查阅。
