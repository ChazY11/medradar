"""Compare two blob contents from git refs without writing them to disk.

Usage: python cmp.py <ref1> <path1> <ref2> <path2> [--diff N]
Prints similarity ratio, identical-line counts, and a bounded unified diff
whose hunk headers carry real line numbers for both sides.
"""
import difflib
import subprocess
import sys

GIT = ["git", "-C", r"<REDACTED_LOCAL_PATH>"]


def show(ref, path):
    p = subprocess.run(GIT + ["show", f"{ref}:{path}"], capture_output=True, text=True, errors="replace")
    if p.returncode != 0:
        raise SystemExit(f"git show failed: {ref}:{path}\n{p.stderr}")
    return p.stdout


def main():
    a_ref, a_path, b_ref, b_path = sys.argv[1:5]
    limit = 60
    if "--diff" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--diff") + 1])
    a, b = show(a_ref, a_path), show(b_ref, b_path)
    al, bl = a.splitlines(), b.splitlines()
    sm = difflib.SequenceMatcher(None, al, bl, autojunk=False)
    print(f"A {a_ref}:{a_path}  {len(al)}L {len(a)}B")
    print(f"B {b_ref}:{b_path}  {len(bl)}L {len(b)}B")
    print(f"similarity={sm.ratio():.3f} identical_lines={sum(x.size for x in sm.get_matching_blocks())}")
    diff = list(difflib.unified_diff(al, bl, fromfile=f"{a_ref}:{a_path}", tofile=f"{b_ref}:{b_path}", lineterm="", n=2))
    print(f"diff_lines={len(diff)}")
    for line in diff[:limit]:
        print(line[:200])
    if len(diff) > limit:
        print(f"... {len(diff)-limit} more diff lines")


if __name__ == "__main__":
    main()
