import csv, json, math
from pathlib import Path

base = Path("data/calibration")
LLM = {
 "cal-02": (1, 0.90, "approval"), "cal-09": (1, 0.88, "approval"), "cal-13": (1, 0.85, "approval"),
 "cal-14": (1, 0.85, "approval"), "cal-21": (1, 0.42, "approval"), "cal-24": (1, 0.85, "approval"),
 "cal-15": (-1, 0.82, "crl"), "cal-16": (-1, 0.85, "crl"), "cal-18": (-1, 0.70, "crl"),
 "cal-19": (-1, 0.88, "crl"), "cal-22": (-1, 0.80, "crl"),
 "cal-07": (1, 0.42, "trial_result"), "cal-29": (1, 0.85, "trial_result"), "cal-30": (1, 0.85, "trial_result"),
 "cal-31": (1, 0.35, "trial_result"), "cal-37": (-1, 0.50, "trial_result"), "cal-38": (-1, 0.42, "trial_result"),
 "cal-39": (-1, 0.85, "trial_result"), "cal-40": (-1, 0.90, "trial_result"), "cal-41": (-1, 0.90, "trial_result"),
 "cal-06": (1, 0.17, "earnings"), "cal-17": (0, 0.15, "earnings"), "cal-20": (0, 0.12, "earnings"),
 "cal-26": (0, 0.15, "earnings"), "cal-28": (1, 0.15, "earnings"),
}
llm = {k: {"direction": v[0], "materiality": v[1], "catalyst_type": v[2]} for k, v in LLM.items()}
(base / "llm_verdicts.json").write_text(json.dumps(llm, ensure_ascii=False, indent=1), encoding="utf-8")
heur = {r["id"]: r for r in json.loads((base / "heuristic_verdicts.json").read_text(encoding="utf-8"))}
rows = list(csv.DictReader((base / "ground_truth.csv").open(encoding="utf-8")))

llm_map = {k: (v["direction"], v["materiality"], v["catalyst_type"]) for k, v in llm.items()}
heur_map = {r["id"]: (int(heur[r["id"]]["direction"]), float(heur[r["id"]]["materiality"]), heur[r["id"]]["catalyst_type"]) for r in rows}


def ranks(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            r[order[k]] = avg
        i = j + 1
    return r


def pearson(a, b):
    n = len(a); ma = sum(a) / n; mb = sum(b) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = math.sqrt(sum((x - ma) ** 2 for x in a)); db = math.sqrt(sum((y - mb) ** 2 for y in b))
    return num / (da * db) if da and db else 0.0


def spearman(a, b):
    return pearson(ranks(a), ranks(b))


def prf(y_true, y_pred):
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t != 1 and p == 1)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p != 1)
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


gt_type = [r["gt_type"] for r in rows]
gt_dir = [int(r["gt_direction"]) for r in rows]
gt_mat = [float(r["gt_materiality"]) for r in rows]

summary = {}
for name, src in (("llm", llm_map), ("heuristic", heur_map)):
    typ = [src[r["id"]][2] for r in rows]
    dirn = [src[r["id"]][0] for r in rows]
    mat = [src[r["id"]][1] for r in rows]
    acc_t = sum(1 for a, b in zip(gt_type, typ) if a == b) / len(rows)
    acc_d = sum(1 for a, b in zip(gt_dir, dirn) if a == b) / len(rows)
    sign = [(1 if x > 0 else -1 if x < 0 else 0) for x in dirn]
    acc_sign = sum(1 for a, b in zip(gt_dir, sign) if a == b) / len(rows)
    hi_t = [1 if m >= 0.5 else 0 for m in gt_mat]
    hi_p = [1 if m >= 0.5 else 0 for m in mat]
    p, r, f1 = prf(hi_t, hi_p)
    mae = sum(abs(a - b) for a, b in zip(gt_mat, mat)) / len(rows)
    rho = spearman(gt_mat, mat)
    summary[name] = dict(type_acc=acc_t, dir_acc=acc_d, dir_acc_sign=acc_sign, spearman=rho,
                         mae=mae, hi_p=p, hi_r=r, hi_f1=f1)
    print(f"[{name}] type_acc={acc_t:.3f} dir_acc={acc_d:.3f} sign_acc={acc_sign:.3f} "
          f"spearman={rho:.3f} mae={mae:.3f} hiP={p:.2f} hiR={r:.2f} hiF1={f1:.2f}")

print("\n== per filing ==")
for r in rows:
    i = r["id"]; l = llm[i]; h = heur[i]
    print(f"{i} {r['company'][:26]:26} gt={r['gt_type']:13}{int(r['gt_direction']):+d} {float(r['gt_materiality']):.2f} | "
          f"llm={l['catalyst_type']:13}{l['direction']:+d} {l['materiality']:.2f} | "
          f"heur={h['catalyst_type']:13}{int(h['direction']):+d} {float(h['materiality']):.2f}")

labels = ["approval", "crl", "trial_result", "earnings"]
for name, src in (("LLM", llm_map), ("heuristic", heur_map)):
    print(f"\n== confusion: gt (rows) vs {name} (cols) ==")
    print("gt\\pred " + " ".join(f"{x[:8]:>8}" for x in labels))
    for g in labels:
        row = [sum(1 for r in rows if r["gt_type"] == g and src[r["id"]][2] == p) for p in labels]
        print(f"{g[:8]:8} " + " ".join(f"{n:>8}" for n in row))

json.dump({"n": len(rows), **summary}, open(base / "metrics.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)


