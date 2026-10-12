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
