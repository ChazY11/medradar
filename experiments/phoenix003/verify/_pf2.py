p='verify_final.py'; s=open(p,encoding='utf-8').read()
s=s.replace('import collections\nimport hashlib','import collections\nimport hashlib\nimport itertools')
s=s.replace('collections.groupby(','itertools.groupby(')
open(p,'w',encoding='utf-8').write(s); print('ok')
