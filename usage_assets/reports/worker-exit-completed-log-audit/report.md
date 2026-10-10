# 已标completed证据的worker日志只读审计

观察UTC：2026-10-10T07:46:22.036671+00:00。未读媒体/模型/2230输入，未修改旧状态或运行目录，未启动GPU/DDS。

| 集合 | cases | logs | fatal matches | traceback matches | missing |
| --- | ---: | ---: | ---: | ---: | ---: |
| current629_completed_snapshot | 275 | 550 | 10 | 0 | 0 |
| published17 | 17 | 34 | 0 | 0 | 0 |
| published12 | 12 | 24 | 1 | 0 | 0 |

Native fatal markers found in parent-completed evidence; preserve existing records and withhold stronger worker-exit claims.

原生sim2sim.py:401–407在全部worker已退出后没有最后nonzero门卫。旧parent0/result/artifact门卫通过不能证明每个worker都正常退出；未出现fatal文本也不能倒推返回码0。此审计保留每log SHA、实际readiness PID、sealedlog SHA对照和精确命中行。

- `current629_completed_snapshot` `random_locomotion:0043:cfg0043_stand_2.0s_right_45_0.7s_run_left_90_1.2s_run_left_45_2.3s_stand_2.0s` `simulator`，parent=0，log SHA `0aac48f005078e78482e42c7e87abd02640b4da4d0d1cdb11c4d4e3f9a770136`：
  - line274: `/isaac-sim/python.sh: line 73: 26659 Segmentation fault      (core dumped) $python_exe "${filtered_args[@]}" $args`
  - line275: `There was an error running python`

- `current629_completed_snapshot` `random_locomotion:0081:cfg0081_stand_2.0s_run_left_45_1.2s_right_90_2.7s_run_right_45_2.0s_left_90_0.9s_right_45_1.5s_run_left_45_1.8s_stand_2.0s` `simulator`，parent=0，log SHA `65b5571002ea10026bff3e43d61b10fe97524126f69659c1b85bdc29005b389f`：
  - line274: `/isaac-sim/python.sh: line 73: 33946 Segmentation fault      (core dumped) $python_exe "${filtered_args[@]}" $args`
  - line275: `There was an error running python`

- `current629_completed_snapshot` `low_speed_step:0004:forward_walk0.8s_step0.5s` `simulator`，parent=0，log SHA `d18c65853d582ce410ab7ae19a81c2d28e061f25ea98e37eb6b6d8efab9c8e49`：
  - line274: `/isaac-sim/python.sh: line 73: 38203 Segmentation fault      (core dumped) $python_exe "${filtered_args[@]}" $args`
  - line275: `There was an error running python`

- `current629_completed_snapshot` `low_speed_step:0005:forward_walk0.8s_step1.0s` `simulator`，parent=0，log SHA `a89b0c2318802913efc4fd7023a2577991baa43497ebb3d4ca8f7556a305f83d`：
  - line274: `/isaac-sim/python.sh: line 73: 38388 Segmentation fault      (core dumped) $python_exe "${filtered_args[@]}" $args`
  - line275: `There was an error running python`

- `current629_completed_snapshot` `low_speed_step:0027:left_90_walk0.8s_step1.0s` `simulator`，parent=0，log SHA `c33a11c561f67a13fa1790019396c136d39e09dc6f96acf4f7e98623f627c34a`：
  - line275: `/isaac-sim/python.sh: line 73: 42464 Segmentation fault      (core dumped) $python_exe "${filtered_args[@]}" $args`
  - line276: `There was an error running python`

- `current629_completed_snapshot` `low_speed_step:0038:right_45_walk1.2s_step0s` `simulator`，parent=0，log SHA `3734865a429a92a7e77dbf09f7ab35660031fcff07cd52c8fe3fb85bf08e963b`：
  - line274: `/isaac-sim/python.sh: line 73: 44532 Segmentation fault      (core dumped) $python_exe "${filtered_args[@]}" $args`
  - line275: `There was an error running python`

- `current629_completed_snapshot` `low_speed_step:0049:right_90_walk0.8s_step1.0s` `simulator`，parent=0，log SHA `79441134a81deff3964cf08462f09ab12b5e8fb159168f36c05e7b5f512d2c02`：
  - line274: `/isaac-sim/python.sh: line 73: 46522 Segmentation fault      (core dumped) $python_exe "${filtered_args[@]}" $args`
  - line275: `There was an error running python`

- `current629_completed_snapshot` `high_speed_step:0039:run_right_45_0.9s_step0s` `simulator`，parent=0，log SHA `abb25dcc6b18ee4e0e4dcf01388fbf68d63feb22415e243af29181532c5a1d43`：
  - line274: `/isaac-sim/python.sh: line 73: 55571 Segmentation fault      (core dumped) $python_exe "${filtered_args[@]}" $args`
  - line275: `There was an error running python`

- `current629_completed_snapshot` `high_speed_step:0054:run_right_90_1.2s_step0s` `simulator`，parent=0，log SHA `526c5f771b2328380048efb5c136d29f56759286b33755265e6bc92e1098ee09`：
  - line274: `/isaac-sim/python.sh: line 73: 58389 Segmentation fault      (core dumped) $python_exe "${filtered_args[@]}" $args`
  - line275: `There was an error running python`

- `current629_completed_snapshot` `low_speed_climb_58:0004:forward_walk1.5s_plat0s` `simulator`，parent=0，log SHA `8b77fe29594ce3112131d87536c779c653113ed055bf35edcc8bea28ecad1062`：
  - line274: `/isaac-sim/python.sh: line 73: 60262 Segmentation fault      (core dumped) $python_exe "${filtered_args[@]}" $args`
  - line275: `There was an error running python`

- `published12` `command-02` `simulator`，parent=0，log SHA `fdae9bf151ff9cb0a30625fdca5f49b9937a52b03871c2b0c7babf3c3e8ab394`：
  - line468: `/isaac-sim/python.sh: line 73:  8467 Segmentation fault      (core dumped) $python_exe "${filtered_args[@]}" $args`
  - line469: `There was an error running python`
