# Git 权限归一化实测
+
+独立复制 student-transfer-cpu-actual-02 全包，将所有出版文件按 Git 克隆权限归一化为 0644/0755。
+父包外部 seal 核验真实退出 0，独立 model-payload 恢复 4 个 ONNX 并逐一匹配原 32 文件回传 SHA，真实退出 0。
+错误 executable bit、坏 seal、额外文件、symlink 四个独立负例均实际退出 1，且未创建恢复目录。
+本旁包只保存执行原件，不复制合成负例模型。v1/v2 原封包均未修改；模型物理验收仍 pending。
+
+完整实际命令、外部 seal 与恢复 SHA 见 [execution.json](execution.json)。本旁包完整性可用 verify_package.py 和外部已审查的本旁包 manifest SHA 核验。
+