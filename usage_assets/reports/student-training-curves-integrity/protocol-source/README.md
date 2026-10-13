本目录仅准备一个CPU TFRecord协议验证phase，未执行或import新harness/科学包，未生成fixture、未读取真实事件、未运行Docker/SSH。AST与原始源byteexact核对不构成协议通过；未来actual结果在protocol-plan.json全部null。既有cpu-v1/v2完全不改。

未来Root在固定image2be的新runc、networknone、GPUhidden、2CPU/12GB容器中执行protocol-plan.json的future_cli；/code挂本harness与冻结v2 extractor只读，/artifacts挂Root给定teacher-high-climb正式原event只读，新空/validation可写。这里没有Docker/host/SSH执行器。需要显式--extractor/--extractor-sha256及--event/--event-bytes/--event-sha256，v2 SHA与Root给定teacher事件basename/72,561,360B/ca862...固定核验；不占原训练容器、没有学生manifest或模型加载。

该单phase与未来学生extract+plot两个phase不同。harness以CPUguard后导入的TensorBoard RecordWriter独立生成raw TFRecords，payload明确是synthetic_protocol_fixture字节，不是学生scalars/protobuf/原生训练回执。20项协议case覆盖valid single/multiple/empty payload/1MiB跨chunk，短header/lenCRC/body/bodyCRC，lengthCRC/bodyCRC与body数据位翻转，完整有效record后追加坏尾/坏record，64MiB长度越界/超过文件长度，wholeSHA/size错与空文件。每个预期失败必须得到实际failed及准确problem/offset/已完整prefix record数；原fixture与verify_tfrecord结果均保留。

另有CRC32C knownvector123456789=0xe3069283、同向量分块更新、masked empty CRC32C三项，不能只靠writer与reader同错而称通过。真实教师原event是另一独立real_teacher_event条目，只验原SHA/size、全部record framing/CRC和完整EOF，绝不伪造或解析正式学生loss/reward，也不宣称9999/29999、7PT、收敛、策略质量或全官方流程通过。

只有读取到SHA已核原字节之后才加载v2私有module，sys.dont_write_bytecode=True，不执行其main/extract/plot，只调用verify_tfrecord。新report为/validation/protocol.json，phase=tfrecord_protocol_validation，status=passed_protocol_validation或failed_protocol_validation，不使用student_training_scalars。全部outcomes/offset/源指纹与actual输入前后指纹保留。现装TensorBoard pywrap_tensorflow.py与record_writer.py逐原bytes复制到/validation/runtime-sources，report列原路径→保留路径与SHA/bytes；失败raw/partial不删除。Root实际父wait/容器身份、隔离和终态需另归档，不能从report自报字段代替OS退出证据。

source-original仅保留固定v2 extractor及其manifest/独审直接原件；minimal-delta/full.diff为从空文件到新harness的完整source diff。protocol-plan.json列完整case/接口/未来null和Root提供event事实，source-manifest逐件SHA。RecordWriter API依据[上游官方源码](https://raw.githubusercontent.com/tensorflow/tensorboard/master/tensorboard/summary/writer/record_writer.py)，引用master只说明接口，未冒充镜像已实测版本；未来actualinstalled源copy记录实际字节。

这是source-only待Root审/执行的协议测试，不是已运行的测试或学生最终验收。没有改H、Git、项目docs/README、armed pair gate、旧源或任何运行作业。
