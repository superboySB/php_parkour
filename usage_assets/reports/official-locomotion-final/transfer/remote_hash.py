import hashlib,json,os,stat,sys
result=[]
for name in sys.argv[1:]:
    before=os.lstat(name)
    if not stat.S_ISREG(before.st_mode):
        raise ValueError("Regular observed artifact required: "+name)
    h=hashlib.sha256()
    with open(name,"rb") as stream:
        for block in iter(lambda:stream.read(1024*1024),b""):
            h.update(block)
    after=os.lstat(name)
    identity=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns,s.st_mode)
    if identity(before)!=identity(after):
        raise ValueError("Source changed while hashing: "+name)
    result.append({"path":name,"bytes":after.st_size,"sha256":h.hexdigest()})
print(json.dumps(result,sort_keys=True))
