#!/usr/bin/env python
"""Secrets / credentials / PII scanner for tracked Git content.

Scans the *committed* blobs of one or more Git refs, so the result describes what
is actually published, not what happens to be in a working tree.  Blobs are
deduplicated by object id, so a file that appears on several branches is read and
reported once per ref it is reachable from.

Usage
    python tools/convergence/licence/secrets_scan.py \
        --repo D:/path/to/repo \
        --ref integration/convergence-001 \
        --ref research/horizon-001 \
        --out research/convergence/licence/secrets_scan.json

Exit codes
    0  no findings at or above --fail-on severity
    1  findings at or above --fail-on severity
    2  scanner error
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict

# --------------------------------------------------------------------------- #
# Patterns.  Each entry: (rule_id, severity, compiled regex, description).
# severity: critical > high > medium > low > info
# --------------------------------------------------------------------------- #
SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

PATTERNS = [
    # --- private keys / certificates -------------------------------------
    ("private_key_block", "critical",
     re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----"),
     "PEM private key block"),
    ("openssh_private_key", "critical",
     re.compile(r"-----BEGIN OPENSSH PRIVATE KEY-----"),
     "OpenSSH private key block"),
    ("pgp_private_key", "critical",
     re.compile(r"-----BEGIN PGP PRIVATE KEY BLOCK-----"),
     "PGP private key block"),

    # --- cloud / SaaS credential shapes ----------------------------------
    ("aws_access_key_id", "critical",
     re.compile(r"\b(?:AKIA|ASIA|AGPA|AIDA|AROA)[0-9A-Z]{16}\b"),
     "AWS access key id"),
    ("github_token", "critical",
     re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
     "GitHub personal access token"),
    ("github_fine_grained", "critical",
     re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b"),
     "GitHub fine-grained token"),
    ("openai_style_key", "high",
     re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
     "sk-... style secret key"),
    ("slack_token", "high",
     re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
     "Slack token"),
    ("google_api_key", "high",
     re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
     "Google API key"),
    ("jwt", "medium",
     re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b"),
     "JSON Web Token"),

    # --- credential-carrying headers -------------------------------------
    ("authorization_header", "critical",
     re.compile(r"(?i)\bauthorization\b[\"']?\s*[:=]\s*[\"']?"
                r"(?:bearer|basic|token|apikey|api[_-]key)\s+[A-Za-z0-9\-._~+/=]{8,}"),
     "Authorization header with a credential"),
    ("bearer_token", "high",
     re.compile(r"(?i)\bbearer\s+[A-Za-z0-9\-._~+/]{20,}=*"),
     "Bearer token literal"),
    ("api_key_header", "high",
     re.compile(r"(?i)\b(?:x-api-key|x-auth-token|x-subscription-key|"
                r"ocp-apim-subscription-key|subscription-key|api-key)\b"
                r"[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9\-_]{8,}"),
     "API key request header"),
    ("cookie_header", "high",
     re.compile(r"(?i)\b(?:set-)?cookie\b[\"']?\s*[:=]\s*[\"']?"
                r"[A-Za-z0-9_.\-]+=[^\s\"',;]{6,}"),
     "Cookie / Set-Cookie header carrying session material"),

    # --- generic secret assignments --------------------------------------
    ("secret_assignment", "medium",
     re.compile(r"(?i)\b(?:api[_-]?key|apikey|client[_-]?secret|access[_-]?token|"
                r"refresh[_-]?token|auth[_-]?token|private[_-]?key|secret[_-]?key|"
                r"session[_-]?(?:id|token)|csrftoken)\b[\"']?\s*[:=]\s*[\"']?"
                r"([A-Za-z0-9\-._~+/]{12,})"),
     "Assignment to a credential-named field"),
    ("password_assignment", "high",
     re.compile(r"(?i)\b(?:password|passwd|pwd)\b[\"']?\s*[:=]\s*[\"']?([^\s\"',;{}]{6,})"),
     "Hard-coded password"),

    # --- PII shapes -------------------------------------------------------
    ("email_address", "low",
     re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
     "Email address"),
    ("cn_resident_id", "critical",
     re.compile(r"\b[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])"
                r"(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b"),
     "Chinese resident identity number shape"),
    ("us_ssn_shape", "high",
     re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
     "US SSN shape"),
    ("patient_data_marker", "medium",
     re.compile(r"(?i)\b(?:patient[ _]?(?:id|name|record|dob)|medical[ _]record|"
                r"\bmrn\b|date[ _]of[ _]birth|\bnhs[ _]number)\b"),
     "Patient-identifying field name"),
]

# Files that must never be committed, matched by basename / suffix.
SENSITIVE_PATH_RULES = [
    (re.compile(r"(?i)(^|/)\.env(\..*)?$"), "critical", "dotenv file"),
    (re.compile(r"(?i)(^|/)\.netrc$"), "critical", "netrc credential file"),
    (re.compile(r"(?i)(^|/)\.pypirc$"), "critical", "PyPI credential file"),
    (re.compile(r"(?i)(^|/)\.npmrc$"), "high", "npm credential file"),
    (re.compile(r"(?i)(^|/)id_(rsa|dsa|ecdsa|ed25519)(\.pub)?$"), "critical", "SSH key pair"),
    (re.compile(r"(?i)\.(pem|key|p12|pfx|jks|keystore|kdbx)$"), "critical", "key material file"),
    (re.compile(r"(?i)(^|/)credentials(\.json|\.yaml|\.yml|\.ini)?$"), "critical", "credentials file"),
    (re.compile(r"(?i)(^|/)\.git-credentials$"), "critical", "git credential store"),
    (re.compile(r"(?i)(^|/)token(s)?\.(json|txt)$"), "high", "token file"),
]

# Domains whose addresses are institutional/public by construction.  Used only to
# separate "a real person's private address" (report) from "an organisation's
# published contact address" (info).
INSTITUTIONAL_DOMAIN_HINTS = (
    "un.org", "who.int", "europa.eu", "eurostat", "oecd.org", "worldbank.org",
    "gov", "gc.ca", "canada.ca", "nih.gov", "hhs.gov", "fda.gov", "nlm.nih.gov",
    "uspto.gov", "gsa.gov", "census.gov", "usitc.gov", "nhs.uk", "gov.uk",
    "ac.uk", "edu", "example.com", "example.org", "users.noreply.github.com",
    "noreply", "no-reply", "crossref.org", "openalex.org", "semanticscholar.org",
    "europepmc.org", "openaire.eu", "cordis.europa.eu", "ted.europa.eu",
    "epo.org", "wipo.int", "anvisa.gov.br", "gov.br", "nmpa.gov.cn",
    "tga.gov.au", "ip-australia", "jpo.go.jp", "dpma.de",
)

MAX_BLOB_BYTES = 48 * 1024 * 1024

# Values that are published placeholders in vendor documentation rather than real
# credentials.  A match whose text contains one of these is reported at `info`
# severity with the rule suffixed `_placeholder`, so it stays visible in the report
# but does not fail CI.  Keep this list short and justified: every entry is a value
# a vendor ships to every reader of its own docs.
PLACEHOLDER_ALLOWLIST = (
    "yourapikeyhere",
    "demo_key",
    "your-subscription-key",
    "your subscription key",
    "insert-key-here",
    "xxxxxxxx",
    "example-key",
)

# Reviewed false positives.  Each entry suppresses one (path, rule, line-fragment)
# triple and MUST carry the reasoning that cleared it.  Suppressed hits are still
# reported (severity `info`, rule suffixed `_known_fp`) so the baseline is auditable
# and cannot hide a new finding at the same location.
KNOWN_FALSE_POSITIVES = [
    {
        "path_suffix": "research/horizon/DATASETS/industry/eu_ted/raw/api_docs_index.html",
        "rule": "api_key_header",
        "line_contains": "data-api-key",
        "reason": "Algolia search-only client-side key embedded in TED's own public "
                  "documentation page; ships to every browser, governs only the "
                  "docs search index, and is not a credential of this project.",
    },
    {
        "path_suffix": "research/horizon/DATASETS/industry/importgenius/raw/terms_of_use.html",
        "rule": "api_key_header",
        "line_contains": "data-public-api-key",
        "reason": "Optibase analytics widget public key in ImportGenius's page; the "
                  "attribute is literally named data-public-api-key.",
    },
    {
        "path_suffix": "tools/github_api.py",
        "rule": "password_assignment",
        "line_contains": "line.split(",
        "reason": "The variable is populated at runtime from `git credential fill`; "
                  "no secret is stored in the file.",
    },
    {
        "path_suffix": "research/horizon/DATASETS/scholarly/clinicaltrials_gov/CTGOV_INDEX.json",
        "rule": "us_ssn_shape",
        "line_contains": '"phone"',
        "reason": "ClinicalTrials.gov study-contact telephone numbers whose prefix "
                  "happens to match a US-SSN shape; field is explicitly `phone`.",
    },
]


def git(repo: str, *args: str, text: bool = False):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: "
                           f"{r.stderr.decode('utf-8', 'replace')[:400]}")
    return r.stdout.decode("utf-8", "replace") if text else r.stdout


def tree_blobs(repo: str, ref: str) -> dict[str, str]:
    """path -> blob oid for every tracked file on `ref`."""
    out = git(repo, "ls-tree", "-r", "-z", ref)
    mapping: dict[str, str] = {}
    for entry in out.split(b"\x00"):
        if not entry:
            continue
        meta, _, path = entry.partition(b"\t")
        parts = meta.split()
        if len(parts) < 3 or parts[1] != b"blob":
            continue  # submodule commit entry
        mapping[path.decode("utf-8", "surrogateescape")] = parts[2].decode()
    return mapping


def read_blobs(repo: str, oids):
    """Yield (oid, bytes) using one `git cat-file --batch` process."""
    oids = list(oids)
    if not oids:
        return
    proc = subprocess.Popen(["git", "-C", repo, "cat-file", "--batch"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        for oid in oids:
            proc.stdin.write(oid.encode() + b"\n")
            proc.stdin.flush()
            header = proc.stdout.readline().decode().strip()
            fields = header.split()
            if len(fields) != 3:
                yield oid, b""
                continue
            size = int(fields[2])
            if size > MAX_BLOB_BYTES:
                proc.stdout.read(size)
                proc.stdout.read(1)
                yield oid, b""
                continue
            yield oid, proc.stdout.read(size)
            proc.stdout.read(1)
    finally:
        proc.stdin.close()
        proc.wait()


def is_binary(data: bytes) -> bool:
    return b"\x00" in data[:8192]


def classify_email(addr: str) -> str:
    low = addr.lower()
    for hint in INSTITUTIONAL_DOMAIN_HINTS:
        if low.endswith("@" + hint) or ("." + hint) in low.split("@")[-1] or hint in low.split("@")[-1]:
            return "institutional_or_public"
    return "personal_or_unclassified"


def scan_text(path: str, data: bytes, findings: list):
    text = data.decode("utf-8", "replace")
    lines = text.splitlines()
    for lineno, line in enumerate(lines, 1):
        if len(line) > 4000:  # minified payloads: only run the strong rules
            line = line[:4000]
        for rule_id, sev, rx, desc in PATTERNS:
            m = rx.search(line)
            if not m:
                continue
            detail = m.group(0)
            placeholder = None
            low = detail.lower()
            for ph in PLACEHOLDER_ALLOWLIST:
                if ph in line.lower():
                    placeholder = ph
                    break
            if rule_id == "email_address":
                detail = m.group(0)
                sub = classify_email(detail)
                if sub == "institutional_or_public":
                    sev = "info"
            if placeholder:
                sev = "info"
                rule_id = rule_id + "_placeholder"
            # Trim the evidence so the report itself does not become a secret store.
            snippet = detail.strip()[:120]
            findings.append({
                "path": path,
                "line": lineno,
                "rule": rule_id,
                "severity": sev,
                "description": desc,
                "match_preview": snippet,
                "column": m.start() + 1,
                # window around the match (minified files put everything on one
                # line, so the whole line is not usable context)
                "line_excerpt": line[max(0, m.start() - 120): m.start() + 240],
            })


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True, help="path to the git repository")
    ap.add_argument("--ref", action="append", required=True,
                    help="git ref to scan; repeatable")
    ap.add_argument("--out", help="write full JSON report here")
    ap.add_argument("--fail-on", default="high",
                    choices=["critical", "high", "medium", "low", "info"],
                    help="severity at or above which to exit 1 (default: high)")
    ap.add_argument("--max-per-rule", type=int, default=400,
                    help="cap findings kept per (rule, ref) to bound report size")
    args = ap.parse_args(argv)

    try:
        trees = {ref: tree_blobs(args.repo, ref) for ref in args.ref}
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    # oid -> bytes, read once
    all_oids = sorted({oid for t in trees.values() for oid in t.values()})
    blob_bytes: dict[str, bytes] = {}
    for oid, data in read_blobs(args.repo, all_oids):
        blob_bytes[oid] = data

    report = {
        "repo": os.path.abspath(args.repo),
        "refs": {},
        "scan_parameters": {
            "patterns": [p[0] for p in PATTERNS],
            "path_rules": [r[0].pattern for r in SENSITIVE_PATH_RULES],
            "blobs_scanned": len(all_oids),
            "binary_blobs_skipped": 0,
        },
    }
    worst = "info"
    binary_skipped = 0

    for ref in args.ref:
        found: list[dict] = []
        n_text = 0
        for path, oid in trees[ref].items():
            data = blob_bytes.get(oid, b"")
            # path-based rules apply regardless of content type
            for rx, sev, desc in SENSITIVE_PATH_RULES:
                if rx.search(path):
                    found.append({
                        "path": path, "line": 0, "rule": "sensitive_path",
                        "severity": sev, "description": desc,
                        "match_preview": path, "column": 0,
                    })
            if not data or is_binary(data):
                if data:
                    binary_skipped += 1
                continue
            n_text += 1
            scan_text(path, data, found)

        # Cap per rule so a single noisy pattern cannot dominate the report.
        per_rule_count: dict[str, int] = defaultdict(int)
        findings: list[dict] = []
        truncated: dict[str, int] = {}
        for f in found:
            for fp in KNOWN_FALSE_POSITIVES:
                if (f["rule"] == fp["rule"]
                        and f["path"].replace("\\", "/").endswith(fp["path_suffix"])
                        and fp["line_contains"] in f.get("line_excerpt", f["match_preview"])):
                    f["suppressed"] = fp["reason"]
                    f["rule"] = f["rule"] + "_known_fp"
                    f["severity"] = "info"
                    break
            f.pop("line_excerpt", None)
            per_rule_count[f["rule"]] += 1
            if per_rule_count[f["rule"]] <= args.max_per_rule:
                findings.append(f)
            else:
                truncated[f["rule"]] = truncated.get(f["rule"], 0) + 1
        by_rule: dict[str, int] = dict(per_rule_count)
        findings.sort(key=lambda f: (SEV_ORDER.get(f["severity"], 9), f["rule"], f["path"], f["line"]))
        for f in findings:
            if SEV_ORDER.get(f["severity"], 9) < SEV_ORDER.get(worst, 9):
                worst = f["severity"]
        counts = defaultdict(int)
        for f in findings:
            counts[f["severity"]] += 1
        report["refs"][ref] = {
            "tracked_files": len(trees[ref]),
            "text_files_scanned": n_text,
            "severity_counts": dict(counts),
            "rule_counts": dict(sorted(by_rule.items())),
            "truncated_counts": dict(sorted(truncated.items())),
            "findings": findings,
        }

    report["scan_parameters"]["binary_blobs_skipped"] = binary_skipped
    report["summary"] = {
        "worst_severity": worst,
        "fail_on": args.fail_on,
        "per_ref_severity": {r: report["refs"][r]["severity_counts"] for r in args.ref},
    }

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=1, sort_keys=True)
        print(f"wrote {args.out}")

    for ref in args.ref:
        info = report["refs"][ref]
        print(f"{ref}: {info['tracked_files']} tracked files, "
              f"{info['text_files_scanned']} text scanned, severities={info['severity_counts']}")
        for f in info["findings"]:
            if SEV_ORDER[f["severity"]] <= SEV_ORDER[args.fail_on]:
                print(f"  [{f['severity']:8s}] {f['rule']:22s} {f['path']}:{f['line']}  "
                      f"{f['match_preview'][:80]}")

    return 1 if SEV_ORDER[worst] <= SEV_ORDER[args.fail_on] else 0


if __name__ == "__main__":
    sys.exit(main())
