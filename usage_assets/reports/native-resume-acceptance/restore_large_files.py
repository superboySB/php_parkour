#!/usr/bin/env python3
"""Restore exact chunked files below a fresh chosen directory; no native execution."""
import argparse,hashlib,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--package',type=Path,required=True);p.add_argument('--destination',type=Path,required=True);a=p.parse_args()
root=a.package.resolve(strict=True);destination=a.destination.absolute();destination.mkdir(parents=True,exist_ok=True)
for row in json.loads((root/'large-file-restoration.json').read_bytes())['files']:
 rel=Path(row['restore_relative']);assert not rel.is_absolute() and '..' not in rel.parts
 target=destination/rel;target.parent.mkdir(parents=True,exist_ok=True)
 assert not any(x.is_symlink() for x in [target,*target.parents])
 h=hashlib.sha256();offset=0
 with target.open('xb') as output:
  for chunk in row['chunks']:
   rel=Path(chunk['relative']);assert not rel.is_absolute() and '..' not in rel.parts and offset==chunk['offset']
   data=(root/rel).read_bytes();assert len(data)==chunk['bytes'] and hashlib.sha256(data).hexdigest()==chunk['sha256']
   output.write(data);h.update(data);offset+=len(data)
 assert offset==row['bytes'] and h.hexdigest()==row['sha256']
print('Restored',len(json.loads((root/'large-file-restoration.json').read_bytes())['files']),'byte-exact files; no training started')
