import sys, os, re
sys.path.insert(0, r"D:\DEPPSKK\worktrees\convergence-001\tools\convergence\h2")
import exp_h2_identity_local as M
from collections import Counter

fda, md = M.load()

def tokens_custom(s, stop=M.STOP, minlen=2, need_digit=False):
    s = M.norm(s)
    return {t for t in s.split() if t and t not in stop and len(t) >= minlen and (not need_digit or any(c.isdigit() for c in t))}

def rec_tokens(rec, **kw):
    return tokens_custom(" ".join(M.names_of(rec)), **kw)

variants = {
    "V1_shared_token_ge1_currentSTOP": dict(minlen=2),
    "V2_shared_token_ge1_stopless": dict(minlen=2, stop=set()),
    "V3_shared_token_ge1_len3": dict(minlen=3),
    "V4_shared_token_ge1_digit": dict(minlen=2, need_digit=True),
    "V5_shared_token_ge1_len4": dict(minlen=4),
}
S5_stop = M.STOP
for name, kw in variants.items():
    stop = kw.pop("stop", S5_stop)
    n=0; n_s3=0; n_s5=0; n_both=0
    for r in fda:
        ft = tokens_custom(" ".join(M.names_of(r)), stop=stop, **kw)
        f = M.firm_of(r)
        for q in md:
            mt = tokens_custom(" ".join(M.names_of(q)), stop=stop, **kw)
            inter = ft & mt
            if not inter: continue
            n += 1
            s3 = f is not None and f == M.firm_of(q)
            s5 = len(inter) >= 2
            if s3: n_s3 += 1
            if s5: n_s5 += 1
            if s3 and s5: n_both += 1
    print(f"{name:34s} S2={n:5d}  S2&S3={n_s3:4d}  S2&S5={n_s5:4d}  S2&S3&S5={n_both:4d}   (targets 445/98/161/5)")
print()
# S3 total and S3&S5 total for context
n_s3=0;n_s3s5=0
for r in fda:
    ft = tokens_custom(" ".join(M.names_of(r)))
    f=M.firm_of(r)
    for q in md:
        mt = tokens_custom(" ".join(M.names_of(q)))
        s3 = f is not None and f == M.firm_of(q)
        if s3:
            n_s3+=1
            if len(ft&mt)>=2: n_s3s5+=1
print("S3 total",n_s3,"S3&S5",n_s3s5)
