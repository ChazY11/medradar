"""Read-only git probe helper for the REFOUNDATION-001 architecture audit.

Never writes to git. Only `git show` / `git ls-tree` / `git diff --stat` / `git log`.
Usage:
  python probe.py ls <ref> [path]            # path -> line count + chars
  python probe.py outline <ref> <path>       # def/class/CREATE TABLE/PRIMARY KEY lines
  python probe.py grep <ref> <regex> [path]  # path:line:text matches (bounded)
  python probe.py schema <ref> <path>        # full CREATE TABLE ... ; blocks
  python probe.py sql <ref> <path> [regex]   # table/column/PK summary for SQLite modules
  python probe.py branches                   # ref list + ahead/behind vs origin/main
  python probe.py tree <ref> [path]          # full file list
"""
import re
import subprocess
import sys

GIT = ["git", "-C", r"<REDACTED_LOCAL_PATH>"]


def run(*args):
    p = subprocess.run(GIT + list(args), capture_output=True, text=True, errors="replace")
    return p.stdout


def show(ref, path):
    return run("show", f"{ref}:{path}")


def cmd_ls(ref, path=""):
    out = run("ls-tree", "-r", "-l", ref, "--", path or ".")
    rows = []
    for line in out.splitlines():
        if "\t" not in line:
            continue
        meta, p = line.split("\t", 1)
        parts = meta.split()
        if len(parts) < 4:
            continue
        rows.append((int(parts[3]), p))
    rows.sort(reverse=True)
    print(f"{len(rows)} files under {path or '.'} @ {ref}")
    for size, p in rows:
        text = show(ref, p) if size < 3_000_000 else ""
        print(f"{text.count(chr(10)):7d}L {size:9d}B {p}")
    return rows


def cmd_outline(ref, path):
    src = show(ref, path)
    pat = re.compile(
        r"^(def |class |SCHEMA|CREATE TABLE|CREATE INDEX|    def |[A-Z_]+ = )|"
        r"PRIMARY KEY|SCHEMA_VERSION|__version__|CREATE TRIGGER"
    )
    print(f"# outline {ref}:{path} ({src.count(chr(10))} lines)")
    for i, line in enumerate(src.splitlines(), 1):
        if pat.search(line):
            print(f"{i:5d}: {line[:180]}")


def cmd_grep(ref, regex, path=""):
    out = run("grep", "-n", "-I", "-E", regex, ref, "--", path or ".")
    lines = out.splitlines()
    print(f"# grep {regex!r} {ref}:{path or '.'} -> {len(lines)} hits")
    for line in lines[:400]:
        print(line[:240])
    if len(lines) > 400:
        print(f"... {len(lines) - 400} more")


def cmd_schema(ref, path):
    src = show(ref, path)
    print(f"# schema {ref}:{path}")
    for m in re.finditer(r"CREATE TABLE[^;]*;", src, re.S):
        block = m.group(0)
        start = src.count("\n", 0, m.start()) + 1
        name = re.search(r"CREATE TABLE(?:\s+IF NOT EXISTS)?\s+([\w.\"]+)", block)
        pk = re.findall(r"PRIMARY KEY[^,\n]*", block)
        print(f"\n--- L{start} {name.group(1) if name else '?'}  PK={pk}")
        print("\n".join("    " + x.strip() for x in block.splitlines()))


def cmd_sql(ref, path):
    src = show(ref, path)
    print(f"# sql summary {ref}:{path} ({src.count(chr(10))} lines)")
    for m in re.finditer(r"CREATE TABLE(?:\s+IF NOT EXISTS)?\s+([\w.\"]+)\s*\((.*?)\);", src, re.S):
        name, body = m.group(1), m.group(2)
        cols = [c.strip().split()[0] for c in body.split(",\n") if c.strip() and not c.strip().upper().startswith(("PRIMARY", "FOREIGN", "UNIQUE", "CHECK", "CONSTRAINT"))]
        pk = re.findall(r"PRIMARY KEY\s*\(([^)]*)\)", body)
        print(f"{name}: cols={len(cols)} pk={pk or 'rowid'} :: {', '.join(cols[:14])}")
    triggers = re.findall(r"CREATE TRIGGER(?:\s+IF NOT EXISTS)?\s+([\w]+)", src)
    if triggers:
        print("triggers:", triggers)


def cmd_branches():
    out = run("for-each-ref", "--format=%(refname:short)", "refs/remotes/origin")
    for r in out.splitlines():
        ab = run("rev-list", "--left-right", "--count", f"{r}...origin/main").split()
        if len(ab) == 2:
            print(f"{r:55s} ahead={ab[0]:>5s} behind={ab[1]:>5s}")


def cmd_tree(ref, path=""):
    out = run("ls-tree", "-r", "--name-only", ref, "--", path or ".")
    for line in out.splitlines():
        print(line)


def main():
    cmd = sys.argv[1]
    if cmd == "ls":
        cmd_ls(*sys.argv[2:])
    elif cmd == "outline":
        cmd_outline(sys.argv[2], sys.argv[3])
    elif cmd == "grep":
        cmd_grep(sys.argv[2], sys.argv[3], *(sys.argv[4:5] or [""]))
    elif cmd == "schema":
        cmd_schema(sys.argv[2], sys.argv[3])
    elif cmd == "sql":
        cmd_sql(sys.argv[2], sys.argv[3])
    elif cmd == "branches":
        cmd_branches()
    elif cmd == "tree":
        cmd_tree(sys.argv[2], *(sys.argv[3:4] or [""]))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
