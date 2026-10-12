# 正式两学生全629结果：发布与恢复源码准备

这是 **source-only 发布工具包**，不是正式模型或1258例物理结果包。保存完整53份冻结源码文件（含原manifest）、39个原依赖provider的字节与恢复位置，以及真实源码审查和三组有限CLI操作。官方教师已有3/5完成最终产物CPU验收；其余教师、两正式学生、其官方评估/888逐源尝试、58例与后续两模型各629配置仍待原任务完成。公开ONNX的629结果不能替代正式学生，`quality_verified=false`、`obstacle_course_completion_verified=false`。

源码与原记录保持原字节，拒绝的第一版publisher及修正diff、各独立审查也完整保留。三份工具本身使用宿主标准库 `python3 -S -B`，科学依赖仍在统一Docker中，不要求宿主安装项目包。

- [冻结源码说明与精确CLI](preparation/NOTES.md) · [原52依赖manifest](preparation/preparation-manifest.json)
- [严格真实验收门卫源码](preparation/admission.py) · [双模型图库发布源码](preparation/publisher.py) · [未来完整结果包恢复源码](preparation/restore.py)
- [Root源码准备完成记录](proof/root-source-completion.json) · [独立字节闭包审查](proof/preparation-metadata-review.json)
- [真实publisher帮助：execution/stdout](proof/actual-cli/publisher-cli-help/execution.json) · [原stdout](proof/actual-cli/publisher-cli-help/stdout.raw)
- [真实restore帮助：execution/stdout](proof/actual-cli/restore-cli-help/execution.json) · [原stdout](proof/actual-cli/restore-cli-help/stdout.raw)
- [真实缺前提status退出0](proof/actual-cli/publisher-cli-missing-status/execution.json) · [waiting原stdout](proof/actual-cli/publisher-cli-missing-status/stdout.raw)
- [原provider来源与mode](preparation/dependency-origin-map.json) · [本源码包92路径恢复映射](restore-map.json) · [范围摘要](summary.md) · [外层SHA与mode清单](publication-manifest.json)

三组真实操作仅为两个`--help`和一次缺少实际合同/外层start/exit SHA的`status`。全部actual child.wait为0、site-packages关闭；status返回waiting，没有加载未来实际admission、创建结果目录或启动Docker/native/GPU。原源码说明的历史时态与后来真实CLI记录分别保留。此包未声称实际模型绑定、1258例仿真、完整结果发布、完整结果恢复或浏览器检查通过。

未来发布必须绑定真实最终4ONNX+28JSON、同模型pair的58终态/60ORT与独立后验、新合同/CPU计划、实际outer父wait0、两kind各629原生结果与CPU后验。总计1258配置、2516正常worker/空组、2516唯一宿主writer出生映射、1258段原视频全片解码，并核模型/source/input/plan/seal全哈希与own CID实际停止。不得合成旧schema的父/CPU收据。所有firstattempt、阈值、raw日志及原媒体保真保存；执行完整不证明课程成功、收敛、PT↔ONNX parity或实体G1/D435i成功。

未来完整结果publisher保存全部inventory正文并按内容去重，大raw分块不超过25,000,000字节、保留offset/每块及whole SHA；媒体达到100,000,000字节会明确拒绝，不静默漏页或转码。**本源码包尚未执行这些实际复制或完整恢复。** 源码包只有数MB，也不包含尚不存在的正式模型、629结果、Docker镜像层或原大资产正文。

## 从本源码包恢复固定工具路径

下面是供未来操作员执行的标准库复制步骤，本包制作时没有执行。先独立核对外层`publication-manifest.json`的SHA，然后按`restore-map.json`恢复53个原准备路径和39个原provider目标。相同public文件可供多个原目标使用，各路径独立chmod其记录mode；不恢复uid/gid、不hardlink。目标若已存在，只允许字节与mode完全相同且保持原件；任何差异、symlink、partial/history冲突都停止，不覆盖。复制中断保留partial，不自动重试或声称成功。

Git只保存可执行位，不保存完整读写权限；fresh checkout的公开包文件仅按bytes/SHA验证。`restore-map.json`保存原目标mode，恢复时逐项重建这些mode（不恢复uid/gid）；已有目标的exact mode校验和新目标chmod/后核保持不变。

**先把整个源码包按原字节完整复制到workspace之外的独立目录（例如`/tmp/php-formal-publication-source-package`），在那里核验manifest后再恢复固定ROOT。不能直接以同一workspace内的`usage_assets`包作为该示例的输入：示例有意拒绝package/workspace祖先关系。**

```bash
python3 -S -B - '<ACTUAL_SOURCE_PACKAGE_DIRECTORY>' '<REVIEWED_WORKSPACE>' '<REVIEWED_PUBLICATION_MANIFEST_SHA256>' <<'PY'
from pathlib import Path, PurePosixPath
import hashlib, json, stat, sys
package, workspace = (Path(v).absolute() for v in sys.argv[1:3])
def safe(p):
    assert '..' not in p.parts and not any(q.is_symlink() for q in (p, *p.parents))
    return p
def rel(s):
    p = PurePosixPath(s)
    assert s and not p.is_absolute() and '..' not in p.parts and p.as_posix() == s and s != '.'
    return s
def fp(p):
    safe(p); assert p.is_file()
    raw = p.read_bytes()
    return len(raw), hashlib.sha256(raw).hexdigest(), stat.S_IMODE(p.stat().st_mode)
safe(package); safe(workspace)
assert not workspace.is_relative_to(package) and not package.is_relative_to(workspace)
raw = (package / 'publication-manifest.json').read_bytes()
assert hashlib.sha256(raw).hexdigest() == sys.argv[3]
manifest = json.loads(raw)
assert manifest['status'] == 'source_preparation_only'
files = manifest['files']; assert len({r['relative'] for r in files}) == len(files)
for r in files:
    assert fp(package / rel(r['relative']))[:2] == (r['bytes'], r['sha256'])
assert {p.relative_to(package).as_posix() for p in package.rglob('*') if p.is_file()} == {r['relative'] for r in files} | {'publication-manifest.json'}
assert not any(p.is_symlink() for p in package.rglob('*'))
rows = json.loads((package / 'restore-map.json').read_bytes())['files']
names = {rel(r['workspace_relative']) for r in rows}
assert len(rows) == len(names) == 92
assert all(not any(p.as_posix() in names for p in PurePosixPath(n).parents) for n in names)
for r in rows:
    assert fp(package / rel(r['package_relative']))[:2] == (r['bytes'], r['sha256'])
    target = safe(workspace / r['workspace_relative'])
    if target.exists():
        assert fp(target) == (r['bytes'], r['sha256'], r['mode'])
if not workspace.exists():
    workspace.mkdir(exist_ok=False)
assert workspace.is_dir()
for r in rows:
    target = safe(workspace / r['workspace_relative'])
    if target.exists():
        assert fp(target) == (r['bytes'], r['sha256'], r['mode'])
        continue
    target.parent.mkdir(parents=True, exist_ok=True)
    data = (package / r['package_relative']).read_bytes()
    assert (len(data), hashlib.sha256(data).hexdigest()) == (r['bytes'], r['sha256'])
    with target.open('xb') as f:
        f.write(data)
    target.chmod(r['mode'])
    assert fp(target) == (r['bytes'], r['sha256'], r['mode'])
print('Restored or confirmed 92 source paths only; no science or full-result restoration executed.')
PY
```

这是本源码包的复制方法，**不能调用`preparation/restore.py`恢复本包**：该程序严格只接受未来完整1258例结果manifest，当前source-only manifest应被拒绝。固定原workspace为`/home/dzp/projects/php_parkour`；若复制到其他位置，不会重写JSON或脚本内部绝对路径，字节恢复成功也不等于控制器可直接运行。实际工具仍读取原固定路径，`dependencies/`仅提供原字节来源。未来实际模型/仿真/CPU/publication/restore合同必须另审，不得从占位SHA推导通过。
