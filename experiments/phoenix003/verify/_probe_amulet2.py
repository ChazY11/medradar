import sys,json
sys.path.insert(0,'experiments/phoenix003/verify')
import vcommon as vc
for name in ('ctgov_compact.jsonl.gz','ctgov_ext_compact.jsonl.gz'):
    for r in vc.read_jsonl_gz(vc.DATASET/name):
        if r['nct_id'] in ('NCT02879448','NCT01182441','NCT01784588'):
            print(name)
            print({k:r.get(k) for k in ('nct_id','source_firm','brief_title','official_title','lead_sponsor','collaborators','first_posted','last_update_posted','start_date','results_first_posted')})
print('--- links rows for PP200049 AMULET ---')
for l in open('experiments/phoenix003/EVIDENCE_LINKS.jsonl',encoding='utf-8'):
    r=json.loads(l)
    if r['milestone_key']=='PP200049' and r['matched_token']=='AMULET':
        print(r['tier'],r['evidence_source'],r['evidence_id'],r['evidence_date'],r['lead_days'],r['regulatory_status'],r.get('status_reason'),r['evidence_title'][:80])
print('--- SYMPLICITY verified rows ---')
for l in open('experiments/phoenix003/EVIDENCE_LINKS.jsonl',encoding='utf-8'):
    r=json.loads(l)
    if r['milestone_key']=='PP220026' and r['matched_token']=='SYMPLICITY' and r['tier'].startswith('VERIFIED'):
        print(r['tier'],r['evidence_source'],r['evidence_id'],r['evidence_date'],r['lead_days'],r['regulatory_status'],r.get('status_reason'))
