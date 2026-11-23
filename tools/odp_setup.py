"""Install and validate a USPTO ODP API key, then lock the response schema.

Usage
    python odp_setup.py --key ABC123...        # persist to the user environment
    python odp_setup.py --file key.txt         # read it from a file (keeps it out of history)
    python odp_setup.py --check                # validate whatever is already configured

What it does, in order:
  1. persist the key as a *user* environment variable (not machine-wide, not this shell only),
     so every later run and every tool sees it without a restart of the editor;
  2. call the live API to prove the key is accepted - a key that is stored but rejected is
     worse than no key, because the failure shows up later as "no patents";
  3. dump the real response envelope and the dataset catalogue to
     docs/radar/evidence/odp_schema.json, which is the artifact that lets the parser stop
     guessing about field names.

The one step this cannot do is create the account: registration sits behind an AWS WAF
challenge and requires an e-mail inbox to confirm ownership. Everything after that confirmation
is automated here.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import winreg  # Windows user-environment persistence

from medradar.radar.http import HostPolicy, PoliteFetcher
from medradar.radar.patents import (ENV_USPTO_ODP, UsptoOdpClient, credential_status,
                                    secret_path)

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "docs" / "radar" / "evidence" / "odp_schema.json"


def persist_user_env(name: str, value: str) -> None:
    """Write a user-scope environment variable and refresh this process."""
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0,
                        winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
    os.environ[name] = value


def persist_key_file(name: str, value: str) -> Path:
    """Also write the key to a file the code reads at call time.

    Belt and braces, for a measured reason: a user environment variable written now is invisible
    to shells that are already running, so "saved" and "readable by the next command" would
    otherwise disagree.
    """
    path = secret_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def build_fetcher() -> PoliteFetcher:
    return PoliteFetcher(
        user_agent="MedRadar/0.1 (+https://github.com/ChazY11/medradar; research)",
        policies={"api.uspto.gov": HostPolicy(requests_per_second=1.0)},
        max_requests=20,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key", help="the API key itself")
    parser.add_argument("--file", help="file containing the key")
    parser.add_argument("--check", action="store_true", help="validate the configured key only")
    args = parser.parse_args()

    if not args.check:
        key = (args.key or "").strip()
        if not key and args.file:
            key = Path(args.file).read_text(encoding="utf-8").strip()
        if not key:
            print("no key supplied: use --key or --file", file=sys.stderr)
            return 2
        persist_user_env(ENV_USPTO_ODP, key)
        path = persist_key_file(ENV_USPTO_ODP, key)
        print(f"{ENV_USPTO_ODP} persisted to the user environment and to {path} "
              f"(length {len(key)}, prefix {key[:4]}...). The file makes it visible to shells "
              f"that are already open.")

    status = credential_status()
    print("credential_status:", json.dumps(status, ensure_ascii=False))
    if not status["uspto_odp"]:
        print(f"\n{ENV_USPTO_ODP} is still not set. Register at https://data.uspto.gov, "
              "then re-run with --key.", file=sys.stderr)
        return 2

    client = UsptoOdpClient(build_fetcher())
    report = client.doctor()
    print("\n== live check ==")
    print(json.dumps(report, ensure_ascii=False, indent=2)[:3000])

    ok = bool(report.get("datasets_ok") or report.get("applications_ok"))
    if not ok:
        print("\nThe key was stored but the API did not accept it. Errors above.", file=sys.stderr)
        return 1

    SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCHEMA_PATH.write_text(
        json.dumps({"measured_at_epoch": __import__("time").time(), **report},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nschema evidence written to {SCHEMA_PATH}")
    print("next: the parser can be locked to these field names instead of guessing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
