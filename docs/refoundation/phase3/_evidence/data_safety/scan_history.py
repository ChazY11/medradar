#!/usr/bin/env python3
"""Final data-safety scan of a commit range: every commit, every added/modified
blob, including blobs later replaced, plus binary header sniffing.

Read-only. Never writes outside --out. Never emits a sensitive literal:
  * the restricted Comtrade-derived value is stored only as a salted hash plus
    first/last two characters and counts;
  * PII is reported as counts per category/file, never values;
  * credentials are reported as rule counts only.

Usage:
    python scan_history.py --repo <path> --base <rev> --tip <rev> --out <dir>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from collections import defaultdict

# --------------------------------------------------------------------------- #
# rules
# --------------------------------------------------------------------------- #

# Known UN Comtrade-derived cell. Variants: plain digits, thousands separators,
# and decimal suffixes. We only ever persist a salted hash + first/last 2 chars.
COMT_RX = re.compile(rb"13[,\.\s]?359[,\.\s]?445[,\.\s]?208")
# NOTE: the literal digits are deliberately absent from this source. The salted
# hash is computed from the bytes matched at scan time, never from a constant.

BULK_PATH_RX = [
    ("comtrade_dataset_path", re.compile(
        rb"(?i)un_comtrade|DATASETS/industry/un_comtrade")),
    ("uk_tender_raw_path", re.compile(
        rb"(?i)uk_find_a_tender/raw|award_packages")),
    ("europepmc_abstract_field", re.compile(rb'"abstractText"\s*:')),
    ("job_fulltext_field", re.compile(rb'"job_description"\s*:')),
    ("comtrade_derived_key", re.compile(rb'"comtrade_usd"\s*:\s*-?\d')),
]

# Actual record payload markers — distinguish real restricted DATA from docs that
# merely name restricted file paths in a triage table.
PAYLOAD_MARKER_RX = [
    ("comtrade_record_values", re.compile(
        rb'"primaryValue"\s*:\s*-?\d|"cifvalue"\s*:\s*-?\d|"hs_description"\s*:')),
    ("europepmc_abstract_text", re.compile(rb'"abstractText"\s*:\s*"[^"]{200,}')),
    ("job_description_fulltext", re.compile(rb'"job_description"\s*:\s*"[^"]{500,}')),
]

# Domains that are reserved for documentation/tests — an address there is a
# fixture, not personal data.
FIXTURE_DOMAINS = {"example.invalid", "example.com", "example.org", "example.net",
                   "test.invalid", "localhost"}

EMAIL_RX = re.compile(rb"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE_RX = re.compile(
    rb"(?:\+\d{1,3}[\s\-.]?)?(?:\(\d{2,4}\)[\s\-.]?)?\d{3,4}[\s\-.]\d{3,4}[\s\-.]\d{3,4}")
PHONE_CTX_RX = re.compile(rb'(?i)"(?:phone|telephone|tel|fax|contactPoint)"\s*[:=]')
CONTACT_NAME_RX = re.compile(rb'"contactPoint"\s*:\s*\{[^}]{0,400}?"name"\s*:\s*"([^"]{3,80})"',
                             re.DOTALL)
BUYER_NAME_RX = re.compile(rb'"name"\s*:\s*"([A-Z][a-z]+(?:\s+[A-Z][a-z\.]+){1,3})"')

CRED_RULES = [
    ("private_key_block", re.compile(rb"-----BEGIN (?:RSA |OPENSSH |EC |DSA |PGP )?PRIVATE KEY-----")),
    ("github_token", re.compile(rb"gh[pousr]_[A-Za-z0-9]{36,}")),
    ("aws_access_key_id", re.compile(rb"AKIA[0-9A-Z]{16}")),
    ("openai_style_key", re.compile(rb"\bsk-[A-Za-z0-9_\-]{32,}")),
    ("slack_token", re.compile(rb"xox[abprs]-[A-Za-z0-9\-]{10,}")),
    ("google_api_key", re.compile(rb"AIza[0-9A-Za-z_\-]{35}")),
    ("jwt", re.compile(rb"eyJ[A-Za-z0-9_\-]{12,}\.[A-Za-z0-9_\-]{12,}\.[A-Za-z0-9_\-]{8,}")),
    ("bearer_header", re.compile(rb"(?i)authorization\s*:\s*bearer\s+[A-Za-z0-9._\-]{20,}")),
    ("hardcoded_credential",
     re.compile(rb"(?i)\b(password|passwd|secret|api[_-]?key|access[_-]?token)\b\s*[:=]\s*"
                rb"['\"][^\s'\"]{8,}['\"]")),
]
CRED_PATH_RX = re.compile(rb"(?i)(^|/)\.env(\.|$)|\.(pem|key|p12|pfx|jks|kdbx)$|"
                          rb"(^|/)id_(rsa|ed25519)$|\.git-credentials$")

ABS_PATH_RX = re.compile(
    rb"(?<![A-Za-z0-9+.\-])[A-Za-z]:[\\/]"
    rb"|(?<![A-Za-z0-9_./:\\])/(?:mnt|home)/[A-Za-z0-9_.\-]+/"
    rb"|\\\\\\\\[A-Za-z0-9_.$\-]*(?:wsl|localhost|127\.0\.0\.1)[^\\\"]*\\\\")

BINARY_EXT = {".pkl", ".pickle", ".sqlite", ".sqlite3", ".db", ".zip", ".gz",
              ".parquet", ".png", ".jpg", ".jpeg", ".ico", ".pdf", ".woff", ".woff2",
              ".ttf", ".eot", ".so", ".dll", ".exe", ".class", ".jar", ".npy", ".npz"}

INSTITUTIONAL_DOMAINS = {"un.org", "github.com", "users.noreply.github.com",
                         "proton.me", "example.com", "fda.hhs.gov", "hhs.gov",
                         "nih.gov", "sec.gov", "europa.eu", "who.int"}


def salted(v: str) -> str:
    return hashlib.sha256(("ref003-data-safety-v1|" + v).encode()).hexdigest()


def git(repo, *a, binary=False):
    p = subprocess.run(["git", "-C", repo, *a], capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(f"git {' '.join(a)}: {p.stderr.decode()[:300]}")
    return p.stdout if binary else p.stdout.decode("utf-8", "replace")


# --------------------------------------------------------------------------- #
# inventory
# --------------------------------------------------------------------------- #

def commit_list(repo, base, tip):
    out = git(repo, "log", "--format=%H%x09%P%x09%ad%x09%s", "--date=iso",
              f"{base}..{tip}")
    rows = []
    for line in out.splitlines():
        parts = line.split("\t")
        h, parents, date, subject = (parts + ["", "", ""])[:4]
        rows.append({"sha": h, "parents": parents.split(), "date": date,
                     "subject": subject})
    return rows


def per_commit_blobs(repo, commit):
    """Every added/modified/deleted blob in one commit (merges vs each parent)."""
    raw = git(repo, "diff-tree", "-r", "-m", "--no-commit-id", "--root", "--raw", commit)
    rows = []
    for line in raw.splitlines():
        if not line.startswith(":"):
            continue
        meta, path = line.split("\t", 1)
        fields = meta[1:].split()
        old_sha, new_sha, status = fields[2], fields[3], fields[4]
        rows.append({"path": path, "status": status,
                     "old_blob": None if set(old_sha) == {"0"} else old_sha,
                     "new_blob": None if set(new_sha) == {"0"} else new_sha})
    return rows


def range_blobs(repo, base, tip):
    """All blobs reachable from tip but not base (includes replaced/deleted)."""
    out = git(repo, "rev-list", "--objects", f"{base}..{tip}")
    pairs = {}
    for line in out.splitlines():
        sha, _, path = line.partition(" ")
        pairs[sha] = path or None
    return pairs


def batch_meta(repo, shas):
    """Return {sha: (type, size)} via one cat-file --batch-check."""
    if not shas:
        return {}
    payload = ("\n".join(shas) + "\n").encode()
    p = subprocess.run(["git", "-C", repo, "cat-file", "--batch-check"],
                       input=payload, capture_output=True)
    out = {}
    for line in p.stdout.decode("utf-8", "replace").splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[1] in ("blob", "tree", "commit", "tag"):
            out[parts[0]] = (parts[1], int(parts[2]) if parts[2].isdigit() else -1)
    return out


def batch_bodies(repo, shas, chunk=120):
    """Yield (sha, bytes) for blobs, in chunks to avoid pipe deadlock."""
    for i in range(0, len(shas), chunk):
        part = shas[i:i + chunk]
        payload = ("\n".join(part) + "\n").encode()
        out = subprocess.run(["git", "-C", repo, "cat-file", "--batch"],
                             input=payload, capture_output=True).stdout
        pos = 0
        for sha in part:
            nl = out.find(b"\n", pos)
            if nl < 0:
                break
            head = out[pos:nl].split()
            pos = nl + 1
            if len(head) < 3 or not head[2].isdigit():
                continue
            size = int(head[2])
            body = out[pos:pos + size]
            pos += size + 1
            yield sha, body


# --------------------------------------------------------------------------- #
# scanning
# --------------------------------------------------------------------------- #

def scan_blob(body: bytes, is_binary: bool, findings):
    if is_binary:
        findings["binary_header"] = body[:16].hex()
        return
    # 1. restricted derived value — hash only
    for m in COMT_RX.finditer(body):
        digits = re.sub(rb"[^0-9]", b"", m.group(0))
        findings["restricted_values"].append({
            "rule": "comtrade_derived_value",
            "salted_sha256": salted(digits.decode()),
            "first2": digits[:2].decode(),
            "last2": digits[-2:].decode(),
            "digits_len": len(digits),
        })
    # 2. restricted path references vs actual restricted payload records
    for rule, rx in BULK_PATH_RX:
        n = len(rx.findall(body))
        if n:
            findings["restricted_path_reference"].append({"rule": rule, "count": n})
    for rule, rx in PAYLOAD_MARKER_RX:
        n = len(rx.findall(body))
        if n:
            findings["restricted_payload"].append({"rule": rule, "count": n})
    # 3. PII
    emails = EMAIL_RX.findall(body)
    personal = 0
    institutional = 0
    fixture = 0
    for e in emails:
        dom = e.decode("utf-8", "replace").split("@")[-1].lower()
        if dom in FIXTURE_DOMAINS:
            fixture += 1
        elif dom in INSTITUTIONAL_DOMAINS:
            institutional += 1
        else:
            personal += 1
    if emails:
        findings["pii_email"].append({"count": len(emails),
                                      "personal": personal,
                                      "institutional_or_alias": institutional,
                                      "documentation_fixture": fixture})
    phones = PHONE_RX.findall(body)
    if phones and PHONE_CTX_RX.search(body):
        findings["pii_phone"].append({"count": len(phones),
                                      "phone_context_present": True})
    cp_names = CONTACT_NAME_RX.findall(body)
    if cp_names:
        findings["pii_contact_names"].append({"count": len(cp_names)})
    buyer_names = BUYER_NAME_RX.findall(body)
    if buyer_names and len(buyer_names) >= 3:
        findings["pii_name_list"].append({"count": len(buyer_names)})
    # 4. credentials
    for rule, rx in CRED_RULES:
        n = len(rx.findall(body))
        if n:
            findings["credentials"].append({"rule": rule, "count": n})
    if CRED_PATH_RX.search(body):
        findings["credentials"].append({"rule": "credential_path_name", "count": 1})
    # 5. absolute paths (masked: prefix class only)
    ap = len(ABS_PATH_RX.findall(body))
    if ap:
        findings["absolute_paths"].append({"count": ap})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=r"<WORKTREE>")
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--tip", default="integration/ref003")
    ap.add_argument("--out", default=os.path.dirname(os.path.abspath(__file__)))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    commits = commit_list(args.repo, args.base, args.tip)
    commit_by_sha = {c["sha"]: c for c in commits}

    # blob -> commits where it appears as added/modified (and path)
    blob_commits = defaultdict(list)
    blob_paths = defaultdict(set)
    per_commit = {}
    for c in commits:
        rows = per_commit_blobs(args.repo, c["sha"])
        per_commit[c["sha"]] = {"files_changed": len(rows),
                                "added": sum(1 for r in rows if "A" in r["status"]),
                                "modified": sum(1 for r in rows if "M" in r["status"]),
                                "deleted": sum(1 for r in rows if "D" in r["status"])}
        for r in rows:
            for sha in (r["new_blob"], r["old_blob"]):
                if sha:
                    blob_commits[sha].append(c["sha"])
                    blob_paths[sha].add(r["path"])

    range_objs = range_blobs(args.repo, args.base, args.tip)
    meta = batch_meta(args.repo, sorted(range_objs))
    blob_shas = [s for s, (t, _) in meta.items() if t == "blob"]
    # also include blobs referenced by diff-tree that rev-list may have missed
    for s in blob_commits:
        if s not in meta:
            meta.update(batch_meta(args.repo, [s]))
            if meta.get(s, ("",))[0] == "blob":
                blob_shas.append(s)
    blob_shas = sorted(set(blob_shas))

    findings = []
    for sha, body in batch_bodies(args.repo, blob_shas):
        size = meta.get(sha, ("blob", len(body)))[1]
        path = sorted(blob_paths.get(sha, []))[0] if blob_paths.get(sha) else (range_objs.get(sha) or "")
        ext = os.path.splitext(path)[1].lower()
        is_binary = ext in BINARY_EXT or b"\x00" in body[:200]
        bucket = defaultdict(list)
        scan_blob(body, is_binary, bucket)
        if not bucket:
            continue
        commits_for = sorted(set(blob_commits.get(sha, [])))
        findings.append({
            "blob": sha,
            "path": path,
            "bytes": size,
            "binary": is_binary,
            "commits": commits_for[:5],
            "commit_count": len(commits_for),
            "first_commit_subject": (commit_by_sha.get(commits_for[0], {}).get("subject")
                                     if commits_for else None),
            "findings": dict(bucket),
        })

    # ---- aggregate (never literal values) ----
    agg = defaultdict(int)
    for f in findings:
        for cat, items in f["findings"].items():
            if cat in ("binary_header",):
                continue
            for it in items:
                key = f"{cat}:{it.get('rule', '')}"
                agg[key] += it.get("count", 1)

    restricted = [f for f in findings if "restricted_values" in f["findings"]]
    creds = [f for f in findings if "credentials" in f["findings"]]
    personal_emails = sum(it["personal"] for f in findings
                          for it in f["findings"].get("pii_email", []))
    phones = sum(it["count"] for f in findings
                 for it in f["findings"].get("pii_phone", []))
    contact_names = sum(it["count"] for f in findings
                        for it in f["findings"].get("pii_contact_names", []))
    name_lists = sum(it["count"] for f in findings
                     for it in f["findings"].get("pii_name_list", []))
    payloads = [f for f in findings if "restricted_payload" in f["findings"]]
    refs = [f for f in findings if "restricted_path_reference" in f["findings"]]
    large = []
    for sha, (typ, size) in meta.items():
        if typ != "blob" or size <= 1024 * 1024:
            continue
        body = next((b for s, b in batch_bodies(args.repo, [sha])), b"")
        large.append({"blob": sha[:12], "bytes": size,
                      "path": (sorted(blob_paths.get(sha, []))[0]
                               if blob_paths.get(sha) else (range_objs.get(sha) or "")),
                      "header_hex": body[:16].hex()})
    large.sort(key=lambda x: -x["bytes"])

    pii_lists = personal_emails >= 3 or phones >= 3 or contact_names >= 1 or name_lists >= 3
    blocked = bool(restricted or creds or payloads or pii_lists)
    disposal = []
    if restricted:
        disposal.append("Restricted derived value present in reachable blobs. Do NOT merge. "
                        "Owner decision: drop the offending blob(s) from the PR by rewriting "
                        "the PR branch (history rewrite) or supersede with a fresh sanitized "
                        "commit chain; do not rewrite main. Rotate nothing (no credential).")
    if creds:
        disposal.append("Credential-shaped data present. Rotate the credential first "
                        "(if real), then remove the blob from history before merge.")
    if payloads:
        disposal.append("Actual restricted third-party payload records present. Merge is "
                        "blocked; remove the blobs from the PR branch and re-add only "
                        "derived, non-reproducing aggregates if permitted.")
    if pii_lists:
        disposal.append("Personal-data list present. Merge is blocked; strip contacts or "
                        "replace identifiers with salted hashes in the PR branch.")

    result = {
        "range": {"base": args.base, "tip": args.tip,
                  "tip_sha": git(args.repo, "rev-parse", args.tip).strip()},
        "commits_total": len(commits),
        "merges": sum(1 for c in commits if len(c["parents"]) > 1),
        "objects_in_range": len(range_objs),
        "blobs_scanned": len(blob_shas),
        "blobs_with_findings": len(findings),
        "per_commit_file_counts": per_commit,
        "commits": [{"sha": c["sha"], "parents": c["parents"], "date": c["date"],
                     "subject": c["subject"],
                     "files_changed": per_commit[c["sha"]]["files_changed"]} for c in commits],
        "aggregate_counts": dict(sorted(agg.items())),
        "category_summary": {
            "restricted_value_blobs": len(restricted),
            "restricted_value_occurrences": sum(len(f["findings"]["restricted_values"])
                                                for f in restricted),
            "credential_blobs": len(creds),
            "personal_email_occurrences": personal_emails,
            "institutional_or_alias_email_occurrences": sum(
                it["institutional_or_alias"] for f in findings
                for it in f["findings"].get("pii_email", [])),
            "documentation_fixture_email_occurrences": sum(
                it["documentation_fixture"] for f in findings
                for it in f["findings"].get("pii_email", [])),
            "phone_occurrences_in_context": phones,
            "contactpoint_name_occurrences": contact_names,
            "name_list_occurrences": name_lists,
            "restricted_payload_blobs": len(payloads),
            "restricted_path_reference_blobs": len(refs),
            "absolute_path_occurrences": sum(it["count"] for f in findings
                                             for it in f["findings"].get("absolute_paths", [])),
            "binary_blobs_with_findings": sum(1 for f in findings if f["binary"]),
            "large_binaries_gt_1MiB": len(large),
        },
        "large_binaries": large,
        "verdict": "BLOCKED" if blocked else "PASS",
        "disposal_recommendation": disposal,
        "findings": findings,
    }
    result["finding_set_sha256"] = hashlib.sha256(
        json.dumps(result, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    out = os.path.join(args.out, "data_safety_final.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=1, ensure_ascii=False)

    print(f"range {args.base}..{args.tip} head={result['range']['tip_sha'][:8]}")
    print(f"commits={len(commits)} merges={result['merges']} "
          f"objects={len(range_objs)} blobs_scanned={len(blob_shas)} "
          f"blobs_with_findings={len(findings)}")
    print("category summary:", json.dumps(result["category_summary"], ensure_ascii=False))
    print("aggregate:", json.dumps(result["aggregate_counts"], ensure_ascii=False))
    print("VERDICT:", result["verdict"])
    for d in disposal:
        print("  DISPOSAL:", d)
    print("finding_set_sha256:", result["finding_set_sha256"])
    print("wrote", out)


if __name__ == "__main__":
    main()
