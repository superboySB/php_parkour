未来 888 源片段验收的只读源码资产初始化修复

旧执行器把源码挂成只读，而 Isaac URDF converter 会在 robot.asset.asset_root 下创建 converted_rankN_pidN 并强制转换 USD。修复使用原有可写 /outputs/posttrain-coverage 挂载内独立的 runtime-robot-assets/robots，首次 CPU 准备时复制 G1 URDF 与 34 个引用 mesh，共 35 个原文件。Python 源码仍为只读。

selection、plan、case 升到 schema 2，并共同封存源/副本 SHA、manifest、实际公开 asset-root 覆盖参数、五文件 harness SHA、解析后配置以及 CPU/native 报告。只有转换目录内 USD 和 converter config.yaml/.asset_hash 可增加；原资产改变、链接、其它新增文件或不完整旧副本均拒绝，不会自动覆盖修复。

目标 Docker CPU 测试最终 116/116 通过；初轮 110 通过、1 项异常类型失败的原 XML 保留。最终测试包括真实原生配置解析逐字段比较（仅 asset_root 改变）、35 文件闭包、篡改与路径拒绝、三类计划共享合同、原生三类循环 first-attempt/暖身停止语义。

本报告未运行 GPU、Isaac 初始化、DDS 或云操作，不证明 USD 转换成功或运动技能。旧冻结训练、watch、输出和实际失败证据未改变；后续新快照和真实只读源一例验收由 root 单独安排。
