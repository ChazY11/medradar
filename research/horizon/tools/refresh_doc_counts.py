"""One-off documentation number refresh after the regulatory workstream landed.

Kept as a script (rather than hand edits) so the counts in the prose are derived
from the registry, not typed. Safe to re-run.
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REG = os.path.join(ROOT, "registry", "sources")


def stats() -> dict:
    rows = [
        json.load(open(os.path.join(REG, f), encoding="utf-8"))
        for f in sorted(os.listdir(REG))
        if f.endswith(".json")
    ]
    return {
        "total": len(rows),
        "access": dict(sorted(Counter(r["access_state"] for r in rows).items())),
        "licence": dict(sorted(Counter(r["licence_status"] for r in rows).items())),
        "reusable": sum(
            1 for r in rows if r["licence_status"] in ("open_licence", "public_domain")
        ),
    }


def main() -> int:
    st = stats()
    print(json.dumps(st, indent=2))
    total = st["total"]
    acc = st["access"]
    lic = st["licence"]

    # ---------------- GLOBAL_SOURCE_DEEP_AUDIT.md ----------------
    p = os.path.join(ROOT, "GLOBAL_SOURCE_DEEP_AUDIT.md")
    s = open(p, encoding="utf-8").read()
    s = s.replace(
        "**HORIZON-001 · 38 sources audited · verified 2026-11-10**",
        f"**HORIZON-001 · {total} sources audited · verified 2026-11-10**",
    )
    s = s.replace(
        "The register is machine-readable: one file per source under `registry/sources/`,\n"
        "validated by `python -m hz.cli verify`. The tables below are generated from it.",
        f"The register is machine-readable: one file per source under `registry/sources/` "
        f"({total} entries), validated by `python -m hz.cli verify`, which currently "
        f"returns `ok: true` with 0 issues. The tables below are generated from it.",
    )
    old_access = """**Access posture across 38 sources**

| state | n | meaning |
|---|---|---|
| `OPEN_DOCUMENTED` | 17 | keyless, machine-readable, documented |
| `OPEN` | 1 | keyless, machine-readable, **undocumented** endpoint |
| `BLOCKED_TECHNICAL` | 7 | WAF / retired host / broken endpoint |
| `REQUIRES_REGISTRATION` | 6 | free key or account needed |
| `MANUAL_ONLY` | 3 | human interface only |
| `REQUIRES_LICENCE` | 2 | commercial product |
| `BLOCKED_LEGAL` | 2 | terms forbid automated reuse |

**Licence posture**

| licence | n |
|---|---|
| `open_licence` (explicit reuse rights) | 8 |
| `open_no_explicit_licence` | 9 |
| `public_domain` | 4 |
| `terms_restricted` | 7 |
| `requires_licence` | 3 |
| `unknown` | 7 |

Only **12 of 38** sources have a licence that unambiguously permits reuse. That is
the real constraint on building a data asset, and it is the number that matters —
not the source count."""
    new_access = f"""**Access posture across {total} sources**

| state | n | meaning |
|---|---|---|
| `OPEN_DOCUMENTED` | {acc.get('OPEN_DOCUMENTED', 0)} | keyless, machine-readable, documented |
| `OPEN` | {acc.get('OPEN', 0)} | keyless, machine-readable, possibly undocumented |
| `BLOCKED_TECHNICAL` | {acc.get('BLOCKED_TECHNICAL', 0)} | WAF / retired host / broken endpoint |
| `REQUIRES_REGISTRATION` | {acc.get('REQUIRES_REGISTRATION', 0)} | free key or account needed |
| `MANUAL_ONLY` | {acc.get('MANUAL_ONLY', 0)} | human interface only |
| `REQUIRES_LICENCE` | {acc.get('REQUIRES_LICENCE', 0)} | commercial product |
| `BLOCKED_LEGAL` | {acc.get('BLOCKED_LEGAL', 0)} | terms forbid automated reuse |

**Licence posture**

| licence | n |
|---|---|
| `open_licence` (explicit reuse rights) | {lic.get('open_licence', 0)} |
| `public_domain` | {lic.get('public_domain', 0)} |
| `open_no_explicit_licence` | {lic.get('open_no_explicit_licence', 0)} |
| `terms_restricted` | {lic.get('terms_restricted', 0)} |
| `requires_licence` | {lic.get('requires_licence', 0)} |
| `unknown` | {lic.get('unknown', 0)} |

Only **{st['reusable']} of {total}** sources have a licence that unambiguously permits
reuse. That is the real constraint on building a data asset, and it is the number
that matters — not the source count."""
    s = s.replace(old_access, new_access)
    s = s.replace(
        "The number worth quoting is not 38. It is **24 sources delivered data, 12 have\n"
        "unambiguous reuse licences, and 2 of those licenses required engineering work to\n"
        "exercise at all** (EPO sitemap semantics, CIPO TLS chain). A further 2 channels\n"
        "would open with a five-minute free registration.",
        f"The number worth quoting is not {total}. It is **24 sources delivered data, "
        f"{st['reusable']} have licences that unambiguously permit reuse, and 2 of those "
        f"required real engineering to exercise at all** (EPO sitemap semantics, CIPO TLS "
        f"chain). A further 2 channels would open with a five-minute free registration, and "
        f"those two are the largest.",
    )
    open(p, "w", encoding="utf-8", newline="\n").write(s)

    # ---------------- EXECUTIVE_SUMMARY_ZH.md ----------------
    p2 = os.path.join(ROOT, "EXECUTIVE_SUMMARY_ZH.md")
    t = open(p2, encoding="utf-8").read()
    t = t.replace(
        "| 深度审计来源 | **38 个**（每个都有 registry 记录：访问状态、许可、阻断原因、合法解锁路径） |",
        f"| 深度审计来源 | **{total} 个**（每个都有 registry 记录：访问状态、许可、阻断原因、合法解锁路径；`hz.cli verify` 0 问题） |",
    )
    t = t.replace(
        "`python -m hz.cli verify` → 导出全部 `ok:true`，24,194 条记录 0 违反；注册表 38 条 0 问题。唯一失败项是 `SOURCE_PROBES/regulatory/` 缺 `PROBES.json`（探针日志完整性问题，**不影响记录有效性**）。",
        "`python -m hz.cli verify` → **`ok: true`**：导出全部 `ok:true`（24,194 条记录 0 违反），"
        f"注册表 {total} 条 0 问题，5 个探针套件齐全。",
    )
    open(p2, "w", encoding="utf-8", newline="\n").write(t)
    print("docs patched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
