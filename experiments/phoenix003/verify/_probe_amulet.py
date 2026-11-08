import sys,json,gzip
sys.path.insert(0,'experiments/phoenix003/verify')
import vcommon as vc
for r in vc.read_jsonl_gz(vc.DATASET/'ctgov_compact.jsonl.gz'):
    if r['nct_id']=='NCT02879448':
        print({k:r[k] for k in ('nct_id','source_firm','brief_title','official_title','lead_sponsor','collaborators','first_posted','last_update_posted','interventions')})
# epmc df for SYMPLICITY / AMULET / MELODY
import collections
df=collections.Counter()
for name in ('epmc_compact.jsonl.gz','epmc_ext_compact.jsonl.gz'):
    for r in vc.read_jsonl_gz(vc.DATASET/name):
        if str(r.get('source') or '').upper()=='PAT': continue
        toks=set(vc.tokens(r.get('title') or ''))|set(vc.tokens(r.get('abstract') or ''))
        for k in (r.get('keywords') or []): toks|=set(vc.tokens(str(k)))
        for t in toks: df[t]+=1
for t in ('SYMPLICITY','AMULET','MELODY','OVERALL','WATCHMAN','INTUITY','CAPTURING','TETHERING','POLYSACCHARIDE','EFFICIENT','ORGANS'):
    print(t,'epmc_df=',df.get(t))
