import io, os, re, sys
repo = r"D:\DEPPSKK\worktrees\convergence-001"
src = os.path.join(repo, "research", "horizon", "experiments", "regulatory", "exp_h2_identity.py")
dst = os.path.join(repo, "tools", "convergence", "h2", "exp_h2_identity_local.py")
s = io.open(src, encoding="utf-8").read()

old_hdr = '''HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))  # research/horizon
sys.path.insert(0, ROOT)

from hz.schema import read_jsonl  # noqa: E402

DS = os.path.join(ROOT, "DATASETS", "regulatory")'''
new_hdr = '''HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
ROOT = os.path.join(REPO, "research", "horizon")  # frozen input tree, read-only
DS = os.path.join(ROOT, "DATASETS", "regulatory")
OUT = os.path.join(REPO, "research", "convergence", "h2", "out")


def read_jsonl(path):
    """Local stdlib JSONL loader (replaces hz.schema.read_jsonl verbatim)."""
    out = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out'''
assert old_hdr in s, "header not found"
s = s.replace(old_hdr, new_hdr)

old_out = 'out_path = os.path.join(HERE, "EXP_H2_PAIRS.jsonl")'
assert old_out in s
s = s.replace(old_out, 'out_path = os.path.join(OUT, "recomputed_pairs.jsonl")')
old_sum = 'with open(os.path.join(HERE, "EXP_H2_SUMMARY.json"), "w", encoding="utf-8",'
assert old_sum in s
s = s.replace(old_sum, 'with open(os.path.join(OUT, "recomputed_summary.json"), "w", encoding="utf-8",')
s = s.replace('Run:  python experiments/regulatory/exp_h2_identity.py',
              'Run:  python tools/convergence/h2/exp_h2_identity_local.py')
s = s.replace('"""EXP-H2 — cross-source identity: FDA GUDID x Health Canada MDALL.',
              '"""EXP-H2 — LOCAL REPRODUCTION copy of research/horizon/experiments/regulatory/exp_h2_identity.py.\n\nOnly the loader and the output paths differ from the frozen script; the algorithm is byte-identical.\nOriginal docstring follows.\n\nEXP-H2 — cross-source identity: FDA GUDID x Health Canada MDALL.')
io.open(dst, "w", encoding="utf-8", newline="\n").write(s)
print("wrote", dst, len(s))
