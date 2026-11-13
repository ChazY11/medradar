import json
old=json.load(open('verify/committed_snapshot/FROZEN_RULES.json')) if __import__('os').path.exists('verify/committed_snapshot/FROZEN_RULES.json') else None
new=json.load(open('FROZEN_RULES.json'))
def flat(d,pre=''):
    out={}
    for k,v in d.items():
        if isinstance(v,dict):
            out.update(flat(v,pre+k+'.'))
        else:
            out[pre+k]=v
    return out
if old:
    fo,fn=flat(old),flat(new)
    print('old keys',len(fo),'new keys',len(fn))
    for k in sorted(set(fo)|set(fn)):
        if fo.get(k)!=fn.get(k):
            print('DIFF',k,'old=',fo.get(k),'new=',fn.get(k))
else:
    print('no old rules in snapshot; snapshot dir contents:',__import__('os').listdir('verify/committed_snapshot'))
print('new top-level keys:',list(new.keys()))
print('new amendment/version notes:',{k:new[k] for k in new if 'amend' in k or 'version' in k or 'frozen' in k})
