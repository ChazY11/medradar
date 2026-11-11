import subprocess, sys, re
repo = r"D:\DEPPSKK\worktrees\convergence-001"
listing = subprocess.run(["git","-C",repo,"cat-file","--batch-all-objects","--batch-check=%(objectname) %(objecttype) %(objectsize)"],capture_output=True,text=True,check=True).stdout
objs=[]
for line in listing.splitlines():
    sha,t,sz=line.split()
    if t=="blob" and int(sz)<=3_000_000:
        objs.append((sha,int(sz)))
print("blobs to scan:",len(objs),flush=True)
# batch read
inp="\n".join(sha for sha,_ in objs)+"\n"
p=subprocess.run(["git","-C",repo,"cat-file","--batch"],input=inp.encode(),capture_output=True)
raw=p.stdout
# parse batch: header line 'sha type size\n' then size bytes then \n
pos=0; i=0
markers=[b"EXP-H2",b"EXP_H2",b"signal_sufficiency",b"by_construction_rule",b"HN2_same_model_token",b"HN4_subsidiary"]
hits=[]
while pos < len(raw) and i < len(objs):
    nl=raw.find(b"\n",pos)
    if nl<0: break
    hdr=raw[pos:nl].decode(errors="replace")
    parts=hdr.split()
    if len(parts)<3: break
    sha,typ,size=parts[0],parts[1],int(parts[2])
    body=raw[nl+1:nl+1+size]
    pos=nl+1+size+1
    i+=1
    found=[m.decode() for m in markers if m in body]
    if found:
        hits.append((sha,size,found,body))
print("hits:",len(hits),flush=True)
for sha,size,found,body in hits:
    print("="*70)
    print(sha,size,found)
    text=body.decode("utf-8",errors="replace")
    print(text[:600].replace("\n","\n  ")[:600])
