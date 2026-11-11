import subprocess
repo=r"D:\DEPPSKK\worktrees\convergence-001"
listing=subprocess.run(["git","-C",repo,"cat-file","--batch-all-objects","--batch-check=%(objectname) %(objecttype) %(objectsize)"],capture_output=True,text=True,check=True).stdout
objs=[(l.split()[0],int(l.split()[2])) for l in listing.splitlines() if l.split()[1]=="blob" and int(l.split()[2])<=2_000_000]
inp="\n".join(s for s,_ in objs)+"\n"
raw=subprocess.run(["git","-C",repo,"cat-file","--batch"],input=inp.encode(),capture_output=True).stdout
markers=[b"pair_id",b"signal_set",b"construction_rule",b"build_pairs",b"hard_negative",b"REJECTED"]
pos=0;i=0
while pos<len(raw) and i<len(objs):
    nl=raw.find(b"\n",pos)
    if nl<0: break
    parts=raw[pos:nl].decode(errors="replace").split()
    if len(parts)<3: break
    sha,size=parts[0],int(parts[2]); body=raw[nl+1:nl+1+size]; pos=nl+1+size+1; i+=1
    found=[m.decode() for m in markers if m in body]
    if found and b"EXP" in body.upper() and (b"H2" in body.upper() or b"PAIR" in body.upper()):
        print("="*60); print(sha,size,found); print(body.decode("utf-8",errors="replace")[:900])
