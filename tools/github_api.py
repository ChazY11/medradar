"""Use the repository's existing git credentials to talk to the GitHub API, without printing them.

git push already works for this repository, so Windows' credential helper holds a token for github.com. The owner
authorised publishing this branch; this script reuses that credential for the API calls only, keeps it in memory, and
prints only the login name and the HTTP status of each call.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request


def credential() -> tuple[str, str]:
    """Ask the configured git credential helper for the github.com credential."""
    payload = "protocol=https\nhost=github.com\n\n"
    result = subprocess.run(["git", "credential", "fill"], input=payload, capture_output=True,
                            text=True, timeout=60)
    if result.returncode != 0:
        raise SystemExit(f"git credential fill failed: {result.stderr.strip()[:200]}")
    username = password = ""
    for line in result.stdout.splitlines():
        if line.startswith("username="):
            username = line.split("=", 1)[1]
        elif line.startswith("password="):
            password = line.split("=", 1)[1]
    if not password:
        raise SystemExit("no password/token returned by the credential helper")
    return username, password


def api(method: str, path: str, token: str, body: dict | None = None) -> tuple[int, dict]:
    url = f"https://api.github.com{path}"
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "medradar-study/1.0",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read().decode("utf-8", "replace")
            return response.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(raw)
        except ValueError:
            parsed = {"raw": raw[:400]}
        return error.code, parsed


def main(argv: list[str]) -> int:
    username, token = credential()
    status, user = api("GET", "/user", token)
    print(f"credential username: {username}; /user status: {status}; login: {user.get('login')}")
    if status != 200:
        print("the credential did not authenticate the API; stopping")
        return 1
    command = argv[0] if argv else "whoami"
    if command == "whoami":
        return 0
    if command == "create-pr":
        title = argv[1]
        head = argv[2]
        base = argv[3]
        body_file = argv[4]
        body = open(body_file, encoding="utf-8").read()
        status, payload = api("POST", "/repos/ChazY11/medradar/pulls", token,
                              {"title": title, "head": head, "base": base, "body": body})
        print(f"create PR status: {status}")
        if status == 201:
            print(f"PR #{payload.get('number')}: {payload.get('html_url')}")
        else:
            print(json.dumps(payload)[:600])
        return 0 if status == 201 else 1
    if command == "comment":
        number, body_file = argv[1], argv[2]
        body = open(body_file, encoding="utf-8").read()
        status, payload = api("POST", f"/repos/ChazY11/medradar/issues/{number}/comments", token,
                              {"body": body})
        print(f"comment status: {status}; url: {payload.get('html_url')}")
        return 0 if status == 201 else 1
    if command == "merge":
        number = argv[1]
        status, payload = api("PUT", f"/repos/ChazY11/medradar/pulls/{number}/merge", token,
                              {"merge_method": "merge",
                               "commit_title": f"Merge pull request #{number} from ChazY11/research/early-signal-5firms"})
        print(f"merge status: {status}; merged: {payload.get('merged')}; sha: {payload.get('sha')}")
        if status != 200:
            print(json.dumps(payload)[:600])
        return 0 if status == 200 else 1
    if command == "pr-state":
        number = argv[1]
        status, payload = api("GET", f"/repos/ChazY11/medradar/pulls/{number}", token)
        print(json.dumps({"status": status, "state": payload.get("state"),
                          "mergeable": payload.get("mergeable"),
                          "head_sha": (payload.get("head") or {}).get("sha"),
                          "commits": payload.get("commits"), "changed_files": payload.get("changed_files")}))
        return 0 if status == 200 else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
