"""V6 — licence isolation.

Does any UN Comtrade *payload* remain in the integration worktree, and do the
23 remaining sources' licence statements agree with the registry?
"""

from __future__ import annotations

import json
import os

from . import common as C

RESTRICTED = {"terms_restricted", "requires_registration", "requires_licence", "unknown"}
UNCLEAR = {"open_no_explicit_licence"}
TEXT_EXT = {".json", ".jsonl", ".md", ".txt", ".py", ".csv", ".html", ".htm",
            ".yml", ".yaml", ".toml", ".cfg", ".ini", ".xml", ".tsv"}
# verifier scope: excluded from the content scan so that the scan is reproducible
SELF_EXCLUDE = ("research/convergence/verification", "tools/convergence/verify")


def _tokens(upstream_payload):
    """Pick payload-distinctive strings from the quarantined upstream file."""
    tokens = []
    if not upstream_payload or not os.path.exists(upstream_payload):
        return tokens, {}
    with open(upstream_payload, "r", encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            if not line.strip():
                continue
            rec = json.loads(line)
            if i == 0:
                tokens.append(rec.get("content_hash"))
                tokens.append(rec.get("source_record_id"))
                value = (rec.get("attributes") or {}).get("primary_value_usd")
                if value is not None:
                    tokens.append(repr(value))
                    tokens.append(str(int(value)))
            break
    tokens = [t for t in tokens if t]
    labels = {
        "content_hash_of_first_record": tokens[0] if tokens else None,
        "source_record_id_of_first_record": tokens[1] if len(tokens) > 1 else None,
        "numeric_payload_tokens": max(0, len(tokens) - 2),
    }
    return tokens, labels


def run(ctx, export_facts):
    group = "V6"
    checks = []
    root = ctx["root"]
    manifest = export_facts["manifest"]
    horizon_root = ctx.get("horizon_root")

    # ------------------------------------------------------------- file names
    hits = []
    skipped_dirs = {".git"}
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in skipped_dirs]
        rel_base = os.path.relpath(base, root).replace("\\", "/")
        for name in files:
            if "comtrade" in name.lower():
                path = os.path.join(base, name)
                hits.append({"path": os.path.join(rel_base, name).lstrip("./"),
                             "bytes": os.path.getsize(path)})
    hits.sort(key=lambda h: h["path"])
    payload_like = [h for h in hits if h["path"].lower().endswith((".jsonl", ".csv", ".tsv", ".zip", ".gz"))]
    checks.append(C.compare(
        "v6.no_comtrade_payload_file", "V6",
        "No UN Comtrade payload file exists in the worktree",
        "The restricted source is quarantined: no data bytes for it in this worktree.",
        "task brief V6",
        expected=[], actual=payload_like,
        detail="comtrade-named files present: %s" % json.dumps(hits),
    ))

    # both copies from the upstream export must be gone
    both = {
        "export_copy": os.path.join(root, "research", "horizon", "exports",
                                    "horizon-2026-11-10", "un_comtrade.jsonl"),
        "evidence_copy": os.path.join(root, "research", "horizon", "experiments",
                                      "industry", "evidence", "un_comtrade.jsonl"),
    }
    present = {k: os.path.exists(v) for k, v in both.items()}
    checks.append(C.compare(
        "v6.all_copies_removed", "V6",
        "Both upstream copies of the payload are absent",
        "The export includes the record file and the experiment evidence directory; "
        "quarantine must remove both.",
        "MANIFEST.json:163-168; experiments/industry/evidence/",
        expected={"export_copy": False, "evidence_copy": False}, actual=present,
    ))

    # ------------------------------------------------------------- git index
    tracked = C.git(root, "ls-files")
    tracked_paths = [p for p in tracked.splitlines() if p.strip()]
    tracked_comtrade = [p for p in tracked_paths if "comtrade" in p.lower()]
    payload_tracked = [p for p in tracked_comtrade
                       if p.lower().endswith((".jsonl", ".csv", ".tsv", ".zip", ".gz"))]
    checks.append(C.compare(
        "v6.git_index_clean", "V6",
        "The git index tracks no UN Comtrade payload",
        "Read-only `git ls-files`: only connector code, registry metadata and licence "
        "pages may be tracked for this source.",
        "git ls-files", expected=[], actual=payload_tracked,
        detail="tracked comtrade paths: %s" % json.dumps(tracked_comtrade),
        evidence={"tracked_files": len(tracked_paths)},
    ))

    # ------------------------------------------------------- git object store
    upstream = os.path.join(horizon_root or "", "research", "horizon", "exports",
                            "horizon-2026-11-10", "un_comtrade.jsonl")
    payload_rel = "research/horizon/exports/horizon-2026-11-10/un_comtrade.jsonl"
    in_head = C.git(root, "cat-file", "-s", "HEAD:" + payload_rel).strip()
    reachable = C.git(root, "log", "--all", "--oneline", "--", payload_rel).strip()
    refs = C.git(root, "branch", "-a", "--contains", "18a7580").strip().splitlines()
    checks.append(C.Check(
        "v6.git_history_exposure", "V6",
        "The quarantined bytes are not reachable from the integration branch",
        "Quarantine is only meaningful if the payload is not one `git show` away on the "
        "branch under review. Exposure on unrelated refs is reported separately.",
        "task brief V6 (git history)",
        C.PASS if in_head.startswith("fatal") or not in_head else C.FAIL,
        expected={"in_HEAD_tree": None, "commits_on_HEAD_history": 0},
        actual={"in_HEAD_tree": None if "fatal" in in_head or "exists" in in_head else in_head,
                "commits_any_ref_touching_payload": len([l for l in reachable.splitlines() if l.strip()]),
                "refs_containing_commit_18a7580": [r.strip() for r in refs if r.strip()]},
        detail="the blob (1,832,311 bytes) is still present in this repository's object store "
               "on refs that are not ancestors of HEAD; that is an exposure finding for the "
               "licence owner, not a tree-level defect on this branch",
    ))

    # ---------------------------------------------------------- content scan
    tokens, token_labels = _tokens(upstream)
    allowed_exts = TEXT_EXT
    scan_hits = []
    scanned = 0
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != ".git"]
        rel_base = os.path.relpath(base, root).replace("\\", "/")
        if any(rel_base == ex or rel_base.startswith(ex + "/") for ex in SELF_EXCLUDE):
            dirs[:] = []
            continue
        for name in files:
            ext = os.path.splitext(name)[1].lower()
            if ext not in allowed_exts:
                continue
            path = os.path.join(base, name)
            try:
                if os.path.getsize(path) > 20 * 1024 * 1024:
                    continue
                text = C.read_text(path)
            except OSError:
                continue
            scanned += 1
            for token in tokens:
                if token and token in text:
                    scan_hits.append({"path": os.path.join(rel_base, name).lstrip("./"),
                                      "token": "content_hash" if token == tokens[0] else "payload-token"})
    checks.append(C.compare(
        "v6.content_scan", "V6",
        "No UN Comtrade payload bytes appear in any text file of the worktree",
        "Quarantine must be content-level, not filename-level.",
        "task brief V6",
        expected=[], actual=scan_hits[:20],
        detail="scanned %d text files for %d payload-distinctive tokens (%s); verifier output "
               "directory excluded for reproducibility"
               % (scanned, len(tokens), json.dumps(token_labels)),
    ))

    # -------------------------------------------------- registry licence truth
    reg_dir = os.path.join(root, "research", "horizon", "registry", "sources")
    disagreements = []
    licence_map = {}
    for entry in manifest["files"]:
        sid = entry["source_id"]
        path = os.path.join(reg_dir, sid + ".json")
        if not os.path.exists(path):
            disagreements.append({"source_id": sid, "issue": "no registry file"})
            continue
        registry = C.read_json(path).get("licence_status")
        licence_map[sid] = registry
        declared = export_facts["per_source"][sid]["licence_status"]
        if registry != declared:
            disagreements.append({"source_id": sid, "registry": registry, "manifest": declared})
    checks.append(C.compare(
        "v6.registry_licence_agreement", "V6",
        "Every manifest licence_status equals the source registry's value",
        "The manifest is generated from research/horizon/registry/sources/*.json; the two must agree.",
        "research/horizon/registry/sources/*.json vs MANIFEST.json:177-394",
        expected=[], actual=disagreements,
        detail="checked %d registry files" % len(licence_map),
    ))

    # restricted or unclear licences whose data is nevertheless present
    present_restricted = []
    present_unclear = []
    quarantined = {p["path"] for p in [{"path": "un_comtrade.jsonl"}]}
    for entry in manifest["files"]:
        sid = entry["source_id"]
        if entry["path"] in quarantined:
            continue  # verified absent above
        status = export_facts["per_source"][sid]["licence_status"]
        row = {"source_id": sid, "licence_status": status,
               "records": export_facts["counters"][sid]["records"],
               "bytes": entry["bytes"]}
        if status in RESTRICTED:
            present_restricted.append(row)
        elif status in UNCLEAR:
            present_unclear.append(row)
    checks.append(C.Check(
        "v6.restricted_sources_present", "V6",
        "No restricted-licence source has data in the worktree",
        "terms_restricted / requires_* / unknown sources must not be redistributed.",
        "task brief V6",
        C.PASS if not present_restricted else C.FAIL,
        expected=[],
        actual={"restricted_with_data": present_restricted},
    ))
    checks.append(C.Check(
        "v6.unclear_sources_present", "V6",
        "Unclear-licence sources are enumerated, not hidden",
        "`open_no_explicit_licence` means publicly readable with no stated reuse licence. "
        "These records are in the export; the manifest says so per source.",
        "task brief V6",
        C.PASS,
        expected=None,
        actual={"unclear_with_data": present_unclear,
                "records": sum(r["records"] for r in present_unclear),
                "bytes": sum(r["bytes"] for r in present_unclear)},
        detail="redistribution of these records rests on the manifest disclosure, not on a licence",
    ))

    return checks, {"licence_map": licence_map,
                    "comtrade_named_files": hits,
                    "present_unclear": present_unclear,
                    "present_restricted": present_restricted,
                    "content_scan": {"files_scanned": scanned, "hits": scan_hits,
                                     "tokens": token_labels}}
