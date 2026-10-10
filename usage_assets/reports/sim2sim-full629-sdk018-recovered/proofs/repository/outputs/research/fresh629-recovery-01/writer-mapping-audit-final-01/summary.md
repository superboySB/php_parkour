# 全629原始worker历史映射终态核对

原始629配置均已完成，每例的两份原生启动收据均与case-evidence及独立CPU最终报告的SHA一致。两份已关闭观察流逐行核对后，1258个原始worker中1250个有且仅有一个真实host command_writer映射；8个缺失，严格为high_speed_speed_vault的cfg0004–0007各simulator/inference。多义映射0，PID/出生时间、线程NSpid/NStgid、ownerbirth与hostbirth冲突0。

两段绑定同一CID/image/StartedAt/host init PID与出生时间、冻结observer源码SHA。完整流的实际字节/SHA及首末时间保存在analysis.json；原始137MB流与恢复流仍是外部历史依赖，本次没有复制或修改。将来分块出版需保持其whole-stream SHA闭合。

原session54334实际exit143、旧host running收据保持原样。恢复manager实际wait0，原native daemon0、CPU后验0，两只own容器均已停止。已有CPU报告为629配置/1258正常退出空组worker/629完整视频解码；本审计只核对报告SHA与逐例绑定，没有重新解码。

[analysis.json](analysis.json)保存全部证明文件指纹；[final-original-worker-mappings.json](final-original-worker-mappings.json)是可直接消费的1258行list。每行保留原case/role/PID/birth与entry SHA；缺项mapping_status=missing_historical_observation、mapping_count=0、mappings=[]。后续四例补验只能另存新身份，不能把新birth填回这些原始行。映射缺失表示历史观察缺口，不能据此推断策略或worker失败；执行完成亦不代表技能成功，quality_verified=false。
