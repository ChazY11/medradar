import csv,json,hashlib,collections,subprocess,re,shutil
from pathlib import Path
from datetime import date
O=Path(__file__).resolve().parent;S=O/'source_snapshot/research/studies/early_signal_5firms'
SHA='969fd0cc4fea040cbdb7a518f3c300b9122980b5'
evidence=json.loads((O/'EVIDENCE_EXTRACT.json').read_text(encoding='utf8'))
notes={r['id']:r for r in csv.DictReader((O/'assessments.tsv').open(encoding='utf8'),delimiter='\t')}
original=list(csv.DictReader((S/'HUMAN_REVIEW_WORKSHEET.csv').open(encoding='utf-8-sig',newline='')))
old={r['packet_id']:r for r in original}
logs=json.loads((O/'EXTERNAL_SOURCE_LOG.json').read_text())+json.loads((O/'ADDITIONAL_SOURCE_LOG.json').read_text())
sources={r['id']:r for r in logs}
labels={'R':'Routine Iteration','U':'Uncertain','F':'False Signal / No Confirmed Shift'}
levels={'L':'低','M':'中','H':'高'}
extra={'ES5-017':['MEDTRONIC_VITALFLOW_2024'],'ES5-027':['PHILIPS_KODEX_2019','PHILIPS_KODEX_2022'],'ES5-050':['GE_ETT_2021'],'LT-07':['PLOS_LT07']}
def number(e):
 p=e['payload'];return p.get('k_number') or (p.get('pma_number','')+p.get('supplement_number','')) or p.get('nct_id')
rows=[]
for idx,e in enumerate(evidence):
 pid=e['packet_id'];n=notes[pid];p=e['packet'];v=e['store_event'];islt=pid.startswith('LT')
 ids=[number(v)]+[number(x) for x in e.get('clearance_matches',[])]+extra.get(pid,[])
 refs=[]
 for sid in ids:
  if sid in sources:
   z=dict(sources[sid]);z['source_family']='trial_registry' if sid.startswith('NCT') else ('publication' if sid.startswith('PLOS') else ('company_disclosure' if sid.startswith(('GE_ETT','PHILIPS','MEDTRONIC')) else 'regulatory'))
   if sid=='GE_ETT_2021':z['web_tool_status']='full page retrieved via web tool; direct HTTP download 403';z['local_note']='external_sources/GE_ETT_2021_NOTE.md'
   if z['status']=='retrieved':z['local_file']='external_sources/'+z.get('file',sid+'.pdf')
   refs.append(z)
 reason=n['reason']
 if pid=='ES5-050':reason+=' 公司公告另称2020年11月起已分发该技术，因此2021年监管日期并非最早商业公开/使用日期。'
 flags=[]
 if not islt:
  if p['candidate_alert']['days_since_previous_same_track'] is None:flags.append('LEFT_CENSORED_GAP_NONE')
  if p['company']=='ge_healthcare':flags.append('GE_LINEAGE_REQUIRES_HUMAN_POLICY')
  if p['technology_track']=='medical_ai':flags.append('AI_VS_BROAD_SOFTWARE_TRACK')
  if not e.get('mapping'):flags.append('LOCAL_PRODUCT_CODE_MAPPING_MISSING')
  if v['payload'].get('supplement_type')=='30-Day Notice':flags.append('MANUFACTURING_NOTICE_NOT_NEW_PRODUCT')
  if pid=='ES5-010':flags.append('DE_NOVO_MISRECORDED_AS_510K')
  if pid=='ES5-039':flags.append('FDA_SUMMARY_HTTP_404')
 else:
  flags+=['SYNTHETIC_CLEARANCE_ID_RESOLVED_IN_CURRENT_STORE','CURRENT_TRIAL_VERSION_NOT_HISTORICAL_REPLAY']
  if n['label']=='F':flags.append('UNSUPPORTED_SAME_PROGRAM_INFERENCE')
 r=dict(packet_id=pid,company=p['company'],technology_track=p['technology_track'],origin='small_sample' if islt else 'candidate',
  ai_label=labels[n['label']],ai_label_authority='independent_ai_evidence_review_v1',ai_uncertainty=levels[n['uncertainty']],
  ai_reason=reason,ai_evidence_locator=n['locator'],ai_primary_record=number(v),ai_primary_title=v['title'],
  ai_primary_url=v['url'],ai_event_date=v['event_date'],ai_source_commit=SHA,
  ai_scope='该packet作为技术转向证据的有效性；错配不等于企业无转向' if islt else '该具体监管事件的技术转向/迭代含义，而非整个产品平台的创新程度',
  ai_flags=flags,ai_human_question=n['human_question'],ai_review_date='2026-11-03',ai_reviewer='Codex AI (not a human reviewer)',
  ai_search_scope='读取提交版本packet/规范/工作表；只读本地原始记录；按编号读取FDA原始摘要或PMA；LT另检索CT.gov全文；仅所列案例定向查公司公告/论文，未做穷尽性全网检索',
  ai_sources=refs,ai_evidence_extract_pointer=f'EVIDENCE_EXTRACT.json#/{idx}',
  ai_independent_confirmation_status='未达到Confirmed Shift的全部要求；不得把同源FDA摘要或仅公司/赛道相同的资料当作独立转向确认',
  human_review_status='PENDING_HUMAN_REVIEW',final_label=None,eligible_for_target_b_scoring=False)
 if islt:
  matches=e['clearance_matches'];r['ai_clearance_match_count']=len(matches);r['ai_resolved_clearance_records']=[dict(id=number(x),event_id=x['event_id'],title=x['title'],date=x['event_date'],url=x['url'],product_code=x['product_code']) for x in matches]
  r['ai_trial_to_clearance_calendar_days']=(date.fromisoformat(p['later_clearance']['date'])-date.fromisoformat(p['representative_trial']['date'])).days
  r['original_lead_days']=p['lead_days'];r['ai_declared_lag_days']=30
 else:
  r['ai_prior_same_applicant_code']=[dict(id=number(x),date=x['event_date'],title=x['title'],url=x['url']) for x in e.get('prior_same_applicant_code',[])]
  r['original_gap_days']=p['candidate_alert']['days_since_previous_same_track']
 r['previous_rubric_label']=old[pid]['agent_preliminary_label'];r['ai_changed_from_previous_rubric']=r['previous_rubric_label'].replace(' (agent-preliminary)','')!=r['ai_label']
 rows.append(r)
payload=dict(schema='independent_ai_review_v1',source_repository='ChazY11/medradar',source_branch='research/full-history-v1',source_commit=SHA,
 review_date='2026-11-03 Asia/Shanghai',authority='AI_ONLY_NOT_HUMAN_GOLD_STANDARD',blind_review=False,
 independence_disclosure='另行依据器械内容形成判断；曾读取原工作表及既有AI标签，因此不是盲评、不是独立真人复核，也未使用第二AI评审者。',
 may_score_detectors=False,uncertainty_definition={'低':'关键事件改动或错配有直接材料，少量语义空间；不代表获真人确认','中':'有直接材料但涉及扩展幅度、软件赛道或实体连续性判断','高':'转向阈值/独立确认/具体器械链接/原始摘要仍不足'},
 counts=dict(collections.Counter(r['ai_label'] for r in rows)),company_counts=dict(collections.Counter(r['company'] for r in rows)),rows=rows)
(O/'AI_REVIEW_69.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
flat=[]
for r in rows:
 q=dict(old[r['packet_id']])
 for k in ['ai_label','ai_uncertainty','ai_reason','ai_evidence_locator','ai_primary_record','ai_primary_title','ai_primary_url','ai_flags','ai_human_question','ai_scope','ai_source_commit','ai_reviewer','ai_review_date','ai_search_scope','ai_independent_confirmation_status']:
  q[k]='; '.join(r[k]) if isinstance(r[k],list) else r[k]
 q['ai_sources']=' | '.join(x['url'] for x in r['ai_sources']);q['ai_eligible_for_target_b_scoring']='false';flat.append(q)
# Original row order and all 20 original cells retained verbatim as CSV values.
flatmap={x['packet_id']:x for x in flat};flat=[flatmap[x['packet_id']] for x in original]
with (O/'AI_REVIEW_WORKSHEET.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(flat[0]));w.writeheader();w.writerows(flat)
title=['# 69份packet逐条独立AI复核','',f'固定提交：`{SHA}`。日期：2026-11-03（Asia/Shanghai）。','',
 '**仅AI建议，不是人工金标准；不能用于检测器评分。** 原人工字段保持空白。本复核看过旧标签，不是盲评。低/中/高表示标注不确定性，不是经过校准的概率。',
 '', '对LT的False Signal仅指本packet的证据链不能支持同项目技术转向；不否认试验本身、企业创新或原协议所计算的宽赛道时间顺序。','']
for r in rows:
 title += [f"## {r['packet_id']} · {r['company']} · {r['technology_track']}",'',f"**AI建议：{r['ai_label']}；不确定性：{r['ai_uncertainty']}。**",'',r['ai_reason'],'',
 f"原始记录：{r['ai_primary_record']} — {r['ai_primary_title']}",'',f"证据定位：{r['ai_evidence_locator']}。",'',f"判断范围：{r['ai_scope']}。",'',f"需要真人回答：{r['ai_human_question']}",'']
 for z in r['ai_sources']:
  title.append(f"- [{z['id']}]({z['url']})（{z.get('web_tool_status',z['status'])}）"+(f"；[本地快照]({z['local_file']})" if z.get('local_file') else ''))
 if r.get('ai_resolved_clearance_records'):
  title += ['', '对应监管记录（当前库中同公司×赛道×日期匹配，非原packet唯一主键）：']+[f"- [{z['id']}]({z['url']}) — {z['title']}" for z in r['ai_resolved_clearance_records']]
 title+=['',f"风险标记：{', '.join(r['ai_flags']) or '无额外机器标记'}。",'',f"旧规则标签：{r['previous_rubric_label']}。",'']
(O/'AI_REVIEW_69.md').write_text('\n'.join(title),encoding='utf8')
queue=[r for r in rows if r['ai_uncertainty']=='高']+[r for r in rows if r['ai_label'].startswith('False')]
qtext=['# 优先人工裁决清单','','先处理9个高不确定项目，然后核准8个错配排除；其余52项的逐条问题见主表。所有69项若要成为Target B仍须真人决定。','']
for r in queue:qtext += [f"## {r['packet_id']} — {r['ai_label']}",'',r['ai_reason'],'',f"**请裁决：** {r['ai_human_question']}",'',f"查证位置：{r['ai_evidence_locator']}",'']
(O/'HUMAN_DECISION_QUEUE.md').write_text('\n'.join(qtext),encoding='utf8')
checks=[]
def check(name,value):
 checks.append({'check':name,'passed':bool(value)});assert value,name
check('69 unique packet IDs',len(rows)==len({r['packet_id'] for r in rows})==69)
check('IDs exactly cover source worksheet',set(old)==set(notes)=={r['packet_id'] for r in rows})
for a,b in zip(original,flat):
 check(a['packet_id']+' all original cells preserved',all(a[k]==b[k] for k in a))
check('all human fields remain blank',all(not r[k] for r in flat for k in ['human_label','human_reason','independent_confirmation','reviewer','reviewed_at']))
check('all AI judgments have rationale, locator, uncertainty, question',all(r['ai_reason'] and r['ai_evidence_locator'] and r['ai_uncertainty'] and r['ai_human_question'] for r in rows))
check('no human final labels or scoring authority',all(r['final_label'] is None and not r['eligible_for_target_b_scoring'] for r in rows))
check('nine resolved LT records unique within lookup',all(r['ai_clearance_match_count']==1 for r in rows if r['origin']=='small_sample'))
check('LT lead accounts for original declared 30-day lag',all(r['ai_trial_to_clearance_calendar_days']-30==r['original_lead_days'] for r in rows if r['origin']=='small_sample'))
check('candidate event reference fields match store',all(x['packet']['evidence']['event_id']==x['store_event']['event_id'] and x['packet']['candidate_alert']['event_date']==x['store_event']['event_date'] for x in evidence[:60]))
mf=json.loads((O/'SOURCE_MANIFEST.json').read_text())
check('all pinned source hashes unchanged',all(hashlib.sha256((O/'source_snapshot'/x['path']).read_bytes()).hexdigest()==x['sha256'] for x in mf['files']))
check('all delivered primary download hashes valid',all(hashlib.sha256((O/'external_sources'/x.get('file',x['id']+'.pdf')).read_bytes()).hexdigest()==x['sha256'] for x in logs if x['status']=='retrieved'))
(O/'VALIDATION.json').write_text(json.dumps(dict(passed=True,checks=checks,changed_ai_labels=sum(r['ai_changed_from_previous_rubric'] for r in rows)),ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(dict(counts=payload['counts'],uncertainty=dict(collections.Counter(r['ai_uncertainty'] for r in rows)),validation_checks=len(checks),changed=sum(r['ai_changed_from_previous_rubric'] for r in rows)),ensure_ascii=False))
