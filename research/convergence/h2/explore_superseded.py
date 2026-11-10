import sys, os, re, json, itertools
sys.path.insert(0, os.path.join(r"D:\DEPPSKK\worktrees\convergence-001", "tools", "convergence", "h2"))
import exp_h2_identity_local as M
from collections import Counter, defaultdict

fda, md = M.load()
print("records", len(fda), len(md))

# ---- helpers ----
def split_tokens(v):
    return [p.upper().strip(".-/") for p in re.split(r"[^A-Za-z0-9\-\./]+", str(v)) if p]

def md_text(rec):
    a = rec.get("attributes") or {}
    parts = [rec.get("original_name") or ""]
    for k in ("device_identifier", "licence_name", "trade_name", "licence_number",
              "device_name", "company_name"):
        if a.get(k) not in (None, ""):
            parts.append(str(a[k]))
    return " ".join(parts)

def fda_model_vals(rec):
    a = rec.get("attributes") or {}
    return [a.get("version_model_number"), a.get("catalog_number")]

def fda_text(rec):
    a = rec.get("attributes") or {}
    return " ".join(str(x) for x in (rec.get("original_name"), a.get("brand_name"),
                                     a.get("device_description"), a.get("version_model_number"),
                                     a.get("catalog_number")) if x)

# Precompute per-record firm/tokens/ids once
F = []
for r in fda:
    a = r.get("attributes") or {}
    F.append(dict(r=r, firm=M.firm_of(r), names=M.names_of(r),
                  toks=M.tokens(" ".join(M.names_of(r))),
                  ids=M.official_ids(r), mtext=M.norm(fda_text(r)),
                  ftext=M.norm(md_text(r))))
D = []
for r in md:
    a = r.get("attributes") or {}
    D.append(dict(r=r, firm=M.firm_of(r), names=M.names_of(r),
                  toks=M.tokens(" ".join(M.names_of(r))),
                  ids=M.official_ids(r), mtext=M.norm(md_text(r)),
                  ftext=M.norm(fda_text(r))))

def strict_toks(rec):
    a = rec.get("attributes") or {}
    old = M.MODEL_MODE; M.MODEL_MODE = "strict"
    out = M.model_tokens(a.get("version_model_number"), a.get("catalog_number"), a.get("device_description"))
    M.MODEL_MODE = old
    return out

def lenient_toks(rec):
    a = rec.get("attributes") or {}
    old = M.MODEL_MODE; M.MODEL_MODE = "lenient"
    out = M.model_tokens(a.get("version_model_number"), a.get("catalog_number"), a.get("device_description"))
    M.MODEL_MODE = old
    return out

def md_toks(rec):
    a = rec.get("attributes") or {}
    return M.model_tokens(a.get("device_identifier"), a.get("licence_name"), a.get("trade_name"))

def s2_variants():
    # returns dict name -> function(f, d) -> (bool, shared)
    out = {}
    out["A_current_strict_set_intersect"] = lambda f, d: (bool(strict_toks(f["r"]) & md_toks(d["r"])), strict_toks(f["r"]) & md_toks(d["r"]))
    out["B_current_lenient_set_intersect"] = lambda f, d: (bool(lenient_toks(f["r"]) & md_toks(d["r"])), lenient_toks(f["r"]) & md_toks(d["r"]))
    def generic_intersect(minlen, need_digit):
        def fn(f, d):
            ft = {p for p in split_tokens(" ".join(str(x) for x in M.names_of(f["r"]))) if len(p) >= minlen and (not need_digit or any(c.isdigit() for c in p))}
            dt = {p for p in split_tokens(md_text_of(d)) if len(p) >= minlen and (not need_digit or any(c.isdigit() for c in p))}
            return bool(ft & dt), ft & dt
        return fn
    out["C_any_digit_len2_set"] = generic_intersect(2, True)
    out["D_any_digit_len3_set"] = generic_intersect(3, True)
    out["E_any_digit_len4_set"] = generic_intersect(4, True)
    def numeric_intersect(minlen):
        def fn(f, d):
            ft = {p for p in split_tokens(fda_text(f["r"])) if p.isdigit() and len(p) >= minlen}
            dt = {p for p in split_tokens(md_text_of(d)) if p.isdigit() and len(p) >= minlen}
            return bool(ft & dt), ft & dt
        return fn
    out["F_numeric_len2_set"] = numeric_intersect(2)
    out["G_numeric_len3_set"] = numeric_intersect(3)
    def substring(minlen, need_digit, source):
        def fn(f, d):
            ft = {p for p in split_tokens(fda_text(f["r"])) if len(p) >= minlen and (not need_digit or any(c.isdigit() for c in p))}
            txt = d["mtext"]
            hit = {t for t in ft if t in txt}
            return bool(hit), hit
        return fn
    out["H_substring_strict_in_mdtext"] = lambda f, d: (lambda s: (bool(s), s))({t for t in strict_toks(f["r"]) if t in d["mtext"]})
    out["I_substring_digit4_in_mdtext"] = substring(4, True, "fda")
    out["J_substring_digit3_in_mdtext"] = substring(3, True, "fda")
    return out

def md_text_of(d):
    return d["mtext"]

# For speed, precompute S3/S5/S1 booleans per pair: 320*174 = 55680, fine
variants = s2_variants()
results = {}
for name, fn in variants.items():
    n = 0; n_and_s3 = 0; n_not_s3 = 0
    for f in F:
        for d in D:
            s2, _ = fn(f, d)
            if not s2: continue
            n += 1
            if f["firm"] is not None and f["firm"] == d["firm"]:
                n_and_s3 += 1
            else:
                n_not_s3 += 1
    results[name] = (n, n_and_s3, n_not_s3)
    print(f"{name:40s} S2={n:5d}  S2&S3={n_and_s3:5d}  S2&!S3={n_not_s3:5d}")

# S3 total
n_s3 = sum(1 for f in F for d in D if f["firm"] is not None and f["firm"] == d["firm"])
n_s3_tfs = sum(1 for f in F for d in D
               if (f["r"].get("attributes") or {}).get("target_firm_slice") and
                  (f["r"].get("attributes") or {}).get("target_firm_slice") == (d["r"].get("attributes") or {}).get("target_firm_slice"))
print("S3 full cross product (firm_of):", n_s3)
print("S3 full cross product (target_firm_slice only):", n_s3_tfs)
print("S1 full:", sum(1 for f in F for d in D if any(M.norm(x) and M.norm(x) == M.norm(y) for x in f["names"] for y in d["names"])))
print("S5 full:", sum(1 for f in F for d in D if len(f["toks"] & d["toks"]) >= 2))
print("target: S2=445, S3=365, total=712, R=387, U=325")
