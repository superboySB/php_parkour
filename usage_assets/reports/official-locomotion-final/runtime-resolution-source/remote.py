from pathlib import Path
import json,hashlib
r=Path('/diff/dzp_is_sb/php-parkour-research/source/0093aa40fbae2bcf219d39ace222e0c4d8a71e305551939a5a1b9c0e40c683ab');rel='thirdparty/holosoma/src/holosoma/holosoma/agents/modules/ppo_modules.py';p=r/rel;b=p.read_bytes();m=r/'source-manifest.json';mb=m.read_bytes();d=json.loads(mb);entry=next(x for x in d['files'] if x['path']==rel);assert hashlib.sha256(b).hexdigest()==entry['sha256'];assert p.read_bytes()==b
print(json.dumps({'source_tree':d['source_tree_sha256'],'source_manifest_sha256':hashlib.sha256(mb).hexdigest(),'entry':entry,'source_raw':b.decode(),'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b),'remote_files_modified':False}))
