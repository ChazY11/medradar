p='verify_final.py'; s=open(p,encoding='utf-8').read()
old='''                "match_tokens": set(vc.tokens(r.get("brief_title") or "")) | set.fromkeys(
                    t for x in iv for t in vc.tokens(x)),'''
new='''                "match_tokens": set(vc.tokens(r.get("brief_title") or "")) | {
                    t for x in iv for t in vc.tokens(x)},'''
assert old in s; s=s.replace(old,new)
old2='''    survivors = sorted({r["matched_token"] for r in com_v
                        if my_rare.get(r["matched_token"]) and not r["matched_token"].isupper() is False})'''
new2='''    survivors = sorted({r["matched_token"] for r in com_v if my_rare.get(r["matched_token"])})'''
assert old2 in s; s=s.replace(old2,new2)
# write-json uses default=str -> dict with Path? fine. also manifest self-reference note
open(p,'w',encoding='utf-8').write(s); print('patched')
