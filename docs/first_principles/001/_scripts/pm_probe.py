
import json, time, urllib.parse, urllib.request, sqlite3, re, sys

UA = {"User-Agent":"MedRadar-FP001-independent-research/1.0 (research; contact: local)"}
def get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            if i == tries-1: raise
            time.sleep(1.5*(i+1))

def esearch(term, mindate, maxdate, retmax=100, datetype="edat", sort="pub+date"):
    q = urllib.parse.urlencode({"db":"pubmed","term":term,"retmode":"json","retmax":retmax,
        "datetype":datetype,"mindate":mindate,"maxdate":maxdate,"sort":sort})
    d = json.loads(get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?"+q))
    r = d.get("esearchresult",{})
    return int(r.get("count",0)), [str(x) for x in r.get("idlist",[])]

QUERIES = {
 "oximetry_broad": '("pulse oximetry" OR oximetry OR SpO2 OR "oxygen saturation") AND ("intensive care" OR "critically ill" OR ICU OR "mechanical ventilation" OR "patient monitoring" OR neonatal)',
 "ecg_monitoring": '("electrocardiogram" OR ECG OR arrhythmia OR "cardiac monitoring" OR telemetry) AND ("intensive care" OR ICU OR "bedside monitor" OR "patient monitor" OR "continuous monitoring")',
 "bp_monitoring": '("arterial blood pressure" OR "non-invasive blood pressure" OR NIBP OR "blood pressure monitoring") AND ("intensive care" OR ICU OR "critically ill" OR "invasive monitoring")',
 "neuro_monitoring": '("near-infrared spectroscopy" OR NIRS OR "cerebral oximetry" OR "cerebral oxygenation" OR "continuous EEG" OR "intracranial pressure") AND ("intensive care" OR ICU OR "neurocritical" OR "critically ill")',
 "alarms": '("alarm fatigue" OR "false alarm" OR "alarm management" OR "alarm algorithm" OR "signal quality") AND ("intensive care" OR ICU OR "monitoring")',
 "monitor_validation": '("patient monitor" OR "bedside monitor" OR "vital sign monitor" OR "multiparameter monitor") AND (validation OR accuracy OR performance OR evaluation)',
 "resp_monitoring": '("capnography" OR "respiratory monitoring" OR "etCO2" OR "end-tidal") AND ("intensive care" OR ICU OR "critically ill" OR "mechanical ventilation")',
}
MINDATE, MAXDATE = "2026/10/01", "2026/11/18"
out = {}
for k, term in QUERIES.items():
    count, ids = esearch(term, MINDATE, MAXDATE, retmax=100)
    print(f"{k}: total={count} got={len(ids)}")
    out[k] = {"term":term, "count":count, "ids":ids}
    time.sleep(0.4)
json.dump(out, open(r"D:\DEPPSKK\_fp001\pubmed_probe.json","w",encoding="utf-8"), ensure_ascii=False)
print("saved")
