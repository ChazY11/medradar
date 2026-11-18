
import json, collections
items=json.load(open(r"D:\DEPPSKK\_fp001\sample120.json",encoding="utf-8"))
# label, feed_eligible, priority(H/M/L/-), uncertain?, note
L = {
0:("DIRECT",1,"M",0,"ECG beat classification algorithm"),
1:("DIRECT",1,"M",0,"Smartphone-camera AF detection vs portable ECG, single-patient case"),
2:("DIRECT",1,"M",0,"EEG abnormality detection algorithm"),
3:("DIRECT",1,"M",0,"Non-invasive ICP monitoring algorithm applications"),
4:("DIRECT",1,"M",1,"ICU sensor system for swallowing/cough events - monitoring of non-physiological events"),
5:("TRANSFER",1,"M",0,"rPPG for MRI gating; sensing modality transferable, application is imaging"),
6:("DIRECT",1,"M",0,"FHIR sensor-fusion deterioration platform at the bedside"),
7:("TRANSFER",1,"L",1,"Trustworthy-AI methodology for clinical EEG"),
8:("DIRECT",1,"M",0,"ECG/arrhythmia linked repository, monitoring data resource"),
9:("DIRECT",1,"H",0,"Peripheral perfusion as confounder of ICU SpO2 accuracy"),
10:("DIRECT",1,"M",0,"Wearable ECG arrhythmia detection after COPD exacerbation"),
11:("DIRECT",1,"M",0,"Cerebral NIRS in NICU - modality review"),
12:("DIRECT",1,"M",0,"Cerebral oxygenation monitoring strategies in ICU - review"),
13:("DIRECT",1,"H",0,"Consumer wearable SpO2 agreement across activity and skin pigmentation"),
14:("DIRECT",1,"M",0,"Patient-specific explainable arrhythmia detection"),
15:("DIRECT",1,"L",0,"510(k) K260670 commodity NIBP monitor (Yuwell), 2026-10-28"),
16:("DIRECT",1,"L",0,"510(k) K260671 (MD Diagnostics), capnography-related code CAP"),
17:("DIRECT",1,"M",0,"Continuous EEG targeting framework in neuro ICU"),
18:("DIRECT",1,"M",0,"510(k) K260640 ECG software library (Monebo), 2026-10-23"),
19:("DIRECT",1,"M",0,"Domain-adaptive ECG arrhythmia classification"),
20:("CLINICAL",0,"-",0,"HRV trajectories in preterm infants - clinical developmental question"),
21:("NON_MEDICAL",0,"-",0,"Radar false-alarm elimination (foreign object debris)"),
22:("CLINICAL",1,"L",0,"Early-warning-score escalation debate - scoring, not device"),
23:("CLINICAL",0,"-",0,"Arrhythmia prevalence in stroke using wearable ECG"),
24:("NON_MEDICAL",0,"-",0,"MIMO radar false alarm"),
25:("DIRECT",1,"H",0,"Systematic review/meta-analysis of continuous non-invasive arterial pressure accuracy in critical care"),
26:("NON_MEDICAL",0,"-",0,"False-alarm level order statistics"),
27:("CLINICAL",0,"-",0,"Sedation comparison using NIRS as measurement tool (pharmacology question)"),
28:("DIRECT",0,"-",1,"Title-only 'Alarm fatigue' - probably editorial/letter; alarm domain"),
29:("CLINICAL",0,"-",0,"Alarm-fatigue education intervention"),
30:("DIRECT",1,"M",0,"ECG arrhythmia classification (self-attention autoencoder)"),
31:("NON_MEDICAL",0,"-",0,"Aircraft predictive maintenance false alarm"),
32:("CLINICAL",0,"-",0,"AECG symptoms vs AF episodes, conference abstract"),
33:("NON_MEDICAL",0,"-",0,"Gear vibration false alarm threshold"),
34:("MEDICAL_UNRELATED",0,"-",0,"Oximetry resource availability survey (health system)"),
35:("MEDICAL_UNRELATED",0,"-",0,"Favism case with low SpO2"),
36:("NON_MEDICAL",0,"-",0,"Radar electromagnetic false alarm interference"),
37:("CLINICAL",0,"-",0,"Deep-learning early warning score, cancer patients"),
38:("CLINICAL",1,"L",0,"ICU nurses' experience of false alarms - human factors"),
39:("NON_MEDICAL",0,"-",0,"Criminal liability of expert opinion"),
40:("CLINICAL",0,"-",0,"NEWS predicting readmission"),
41:("CLINICAL",1,"L",0,"Nudge fatigue in digital clinical environments"),
42:("CLINICAL",0,"-",0,"Early warning systems from patient records"),
43:("CLINICAL",0,"-",0,"AKI prediction in ICU sepsis"),
44:("CLINICAL",0,"-",0,"Nocturnal BP pattern and AF recurrence after PVI"),
45:("CLINICAL",0,"-",0,"SaO2/PaO2 and COVID ICU outcome"),
46:("CLINICAL",0,"-",0,"Lactate/ScvO2 as graft predictors"),
47:("CLINICAL",0,"-",0,"Nursing intervention in invasive BP monitoring practice"),
48:("NON_MEDICAL",0,"-",0,"Shewhart process monitoring (industrial statistics)"),
49:("MEDICAL_UNRELATED",0,"-",0,"Propofol/ephedrine haemodynamics"),
50:("MEDICAL_UNRELATED",0,"-",0,"CRT implantation case"),
51:("DIRECT",0,"-",1,"Title-only 'Alarm Management' chapter - ambiguous domain (clinical vs industrial)"),
52:("NON_MEDICAL",0,"-",0,"Wind turbine false alarm detection"),
53:("CLINICAL",0,"-",0,"Connector technique in invasive BP monitoring practice"),
54:("MEDICAL_UNRELATED",0,"-",0,"Clinical case of low oxygen saturation"),
55:("NON_MEDICAL",0,"-",0,"CFAR detection algorithm"),
56:("NON_MEDICAL",0,"-",0,"Industrial alarm correlation"),
57:("MEDICAL_UNRELATED",0,"-",0,"Enflurane haemodynamics"),
58:("DIRECT",1,"M",0,"Remote continuous monitoring with early-warning system, RCT"),
59:("CLINICAL",0,"-",0,"EWS education for nurses"),
60:("CLINICAL",0,"-",0,"Automated alert/MET activation using EWS (logistics, not device)"),
61:("MEDICAL_UNRELATED",0,"-",0,"ECG case of tachycardia"),
62:("CLINICAL",0,"-",0,"Nesting care on vital signs in preterm - care intervention"),
63:("TRANSFER",0,"-",0,"XAI in clinical decision support - generic AI method"),
64:("CLINICAL",0,"-",0,"Venous pO2 and deterioration"),
65:("MEDICAL_UNRELATED",0,"-",0,"Metabolic case report"),
66:("CLINICAL",0,"-",0,"Oxygenation indices for mortality prediction"),
67:("DIRECT",1,"L",1,"Title-only: delayed ECG readings after telehealth outages - workflow failure"),
68:("MEDICAL_UNRELATED",0,"-",0,"Neuromuscular case report"),
69:("CLINICAL",0,"-",0,"Pre-ICU medication vulnerability"),
70:("CLINICAL",0,"-",0,"ML prediction of postoperative complications from EHR"),
71:("TRANSFER",0,"-",0,"Editorial on what medicine asks of AI"),
72:("CLINICAL",0,"-",0,"ICU mortality risk model"),
73:("TRANSFER",1,"L",0,"High-frequency arterial pressure waveform data method from EHR"),
74:("MEDICAL_UNRELATED",0,"-",0,"Endocarditis phenotyping"),
75:("TRANSFER",0,"-",0,"Biomarker ML framework"),
76:("CLINICAL",0,"-",0,"RDW mortality index"),
77:("CLINICAL",0,"-",0,"EHR foundation model generalizability"),
78:("CLINICAL",0,"-",0,"ML mortality model COPD+HF"),
79:("CLINICAL",0,"-",0,"Oxygen saturation targets and mortality"),
80:("DIRECT",1,"H",0,"Occult hypoxaemia in ICU: SpO2 falsely reassuring - device accuracy failure"),
81:("CLINICAL",0,"-",0,"Cardiorenal mortality model"),
82:("CLINICAL",0,"-",0,"ICU prognosis prediction critique"),
83:("MEDICAL_UNRELATED",0,"-",0,"Positioning device case report"),
84:("MEDICAL_UNRELATED",0,"-",0,"External hydrocephalus"),
85:("CLINICAL",0,"-",0,"DO2/VO2 ratio and outcomes"),
86:("MEDICAL_UNRELATED",0,"-",0,"Airway risk stratification"),
87:("MEDICAL_UNRELATED",0,"-",0,"Obstetric case report"),
88:("CLINICAL",0,"-",0,"Neurocritical mortality model"),
89:("CLINICAL",0,"-",0,"Troponin in TBI"),
90:("CLINICAL",0,"-",0,"ICU admission model PTB+KP"),
91:("CLINICAL",0,"-",0,"Brain injury prediction after arrest"),
92:("CLINICAL",0,"-",0,"ROX index and HFNC outcomes"),
93:("MEDICAL_UNRELATED",0,"-",0,"Hospital workforce staffing"),
94:("CLINICAL",0,"-",0,"Unanticipated ICU transfer review"),
95:("DIRECT",0,"-",0,"1988 cardiac monitor clearance K875160 (DRT) - archive"),
96:("DIRECT",0,"-",0,"1990 sleep/respiratory recorder K901466 (BZQ) - archive"),
97:("DIRECT",0,"-",0,"1983 pressure transducer dome K833095 (DRS) - archive"),
98:("DIRECT",0,"-",0,"1990 SpO2 sensor K904185 (DRX) - archive"),
99:("DIRECT",1,"M",0,"2021 mobile respiratory monitor K211387 (BZQ)"),
100:("DIRECT",0,"-",0,"2005 self-check ECG K042254 - archive"),
101:("DIRECT",0,"-",0,"1990 monitoring electrode K903491 - archive"),
102:("DIRECT",0,"-",0,"1984 CO2 gas test K843844 (CCK) - archive"),
103:("DIRECT",1,"M",0,"2015 ViSi Mobile wearable monitoring system K152341 (MWI)"),
104:("DIRECT",1,"L",0,"2007 Mindray PM-9000 patient monitors K070791 (MHX)"),
105:("DIRECT",1,"L",0,"2011 Biocare digital electrocardiograph K101876 (DPS)"),
106:("DIRECT",0,"-",0,"1994 patient-monitor simulator K944257 (DRT) - archive"),
107:("DIRECT",0,"-",0,"1995 Aristo patient monitor K953817 (DQA mismatch) - archive"),
108:("DIRECT",0,"-",0,"1994 ECG electrode K940586 - archive"),
109:("DIRECT",1,"M",0,"2019 AliveCor Triangle System K183319 (DXH)"),
110:("DIRECT",0,"-",0,"1981 disposable pressure transducer K810637 - archive"),
111:("DIRECT",1,"L",0,"2020 Schiller CARDIOVIT K183425 (DPS)"),
112:("DIRECT",0,"-",0,"1995 MemoryTrace arrhythmia monitor K941898 - archive"),
113:("DIRECT",0,"-",0,"2008 BP cuff K071244 - archive"),
114:("DIRECT",1,"H",0,"2026-10-02 wearable blood-oxygen ring clearance K260490 (DQA)"),
115:("MEDICAL_UNRELATED",0,"-",0,"Corporate governance / AGM nominations"),
116:("MEDICAL_UNRELATED",1,"M",1,"Draeger-B.Braun connected acute-care collaboration: commercial signal, no technical evidence"),
117:("MEDICAL_UNRELATED",0,"-",0,"Employer branding post"),
118:("MEDICAL_UNRELATED",0,"-",0,"Philips Sonicare dental advisory board"),
119:("MEDICAL_UNRELATED",0,"-",0,"Service marketing post, no date, no product"),
}
assert len(L)==120, len(L)
out=[]
for i,x in enumerate(items):
    lab,fe,pri,unc,note=L[i]
    out.append({"i":i,"observation_id":x["observation_id"],"source":x["source"],"title":x["title"],
      "pub":x["published_at"] or x["event_at"],"stratum":x["stratum"],"label":lab,"feed_eligible":bool(fe),
      "priority":pri,"uncertain":bool(unc),"note":note,
      "engine_decision":x["engine_decision"],"engine_tier":x["engine_tier"],"engine_category":x["engine_category"],
      "engine_rel":x["engine_dims"].get("monitoring_relevance"),"engine_imp":x["engine_dims"].get("importance")})
json.dump(out, open(r"D:\DEPPSKK\_fp001\labelled120.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
# confusion
c=collections.Counter((o["label"], o["engine_rel"]) for o in out)
labels=["DIRECT","TRANSFER","CLINICAL","MEDICAL_UNRELATED","NON_MEDICAL"]
print("engine monitoring_relevance:", collections.Counter(o["engine_rel"] for o in out))
print()
print("label -> engine_rel")
for lab in labels:
    row={e:c[(lab,e)] for e in labels+[None]}
    print(f"  {lab:17s} n={sum(1 for o in out if o['label']==lab):3d} ", row)
tp=sum(1 for o in out if o["feed_eligible"] and o["engine_decision"]=="FEED")
fp=sum(1 for o in out if not o["feed_eligible"] and o["engine_decision"]=="FEED")
fn=sum(1 for o in out if o["feed_eligible"] and o["engine_decision"]!="FEED")
tn=sum(1 for o in out if not o["feed_eligible"] and o["engine_decision"]!="FEED")
print()
print(f"feed binary: TP={tp} FP={fp} FN={fn} TN={tn} precision={tp/(tp+fp) if tp+fp else None} recall={tp/(tp+fn) if tp+fn else None}")
print()
print("engine importance values:", collections.Counter(o["engine_imp"] for o in out))
print("by source:")
for s in sorted({o["source"] for o in out}):
    sub=[o for o in out if o["source"]==s]
    t=sum(1 for o in sub if o["feed_eligible"] and o["engine_decision"]=="FEED")
    p=sum(1 for o in sub if o["engine_decision"]=="FEED")
    pos=sum(1 for o in sub if o["feed_eligible"])
    print(f"  {s:18s} n={len(sub):3d} labelled+={pos:3d} engine+={p:3d} TP={t}")
