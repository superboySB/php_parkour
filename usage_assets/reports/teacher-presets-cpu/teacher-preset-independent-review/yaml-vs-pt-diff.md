# 六教师YAML与PT配置的精确差异

六份均只有同一处差异：`$.algo.config.module_dict.actor.output_dim[0]`，YAML为字符串`"robot_action_dim"`，PT为整数`29`。无临时motion path、anchor、观测、critic或其他字段差异；原始YAML与PT确实不相等，原报告false保持不变。输入bytes/SHA前后完全一致，CUDA未初始化。

这是原生运行时补全：train_agent.py:324–327先保存YAML，:382再algo.setup，:383才附加checkpoint metadata。PPO.setup将同一actor config传给setup_ppo_actor_module，后者传给PPOActor；ppo_modules.py:40–44原地把output_dim列表中的robot_action_dim替换为num_actions（G1为29）。BaseAlgo:60保存同一experiment对象引用，:67保存其当前serializable dict，因此后续PT记录整数29。

没有由这一处差异证明reload错误：原生PPOActor既可接收未解析token并补全29，也可直接接收29；当前eval_teacher通过checkpoint.py:72–101优先恢复PT内配置，旧文件缺失内嵌配置时才fallback YAML。本轮没有做Isaac reload，也不把参数解析解释为物理验收。

[每份文件、精确类型/值、原字节SHA与源码行号](yaml-vs-pt-diff.json)
