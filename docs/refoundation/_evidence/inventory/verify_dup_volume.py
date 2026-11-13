import subprocess


def sh(*a):
    return subprocess.run(["git", *a], capture_output=True, text=True).stdout


def blobs(ref, paths):
    out = {}
    for p in paths:
        r = subprocess.run(["git", "rev-parse", f"{ref}:{p}"],
                           capture_output=True, text=True)
        if r.returncode == 0:
            out[p] = r.stdout.strip()
    return out


def compare(branch, other, label):
    paths = [p for p in sh("diff", "--name-only", f"origin/main...origin/{branch}").splitlines() if p]
    a = blobs(f"origin/{branch}", paths)
    b = blobs(f"origin/{other}", paths)
    same = diff = only = 0
    for p, h in a.items():
        if p not in b:
            only += 1
        elif b[p] == h:
            same += 1
        else:
            diff += 1
    print(f"{label}: changed={len(paths)} identical={same} differs={diff} absent_in_other={only}")


compare("research/s031-hiring-capability-study", "research/innovation-signals-observatory", "#22 vs #21")
compare("integration/convergence-001", "research/horizon-001", "#30 vs #29")
compare("integration/convergence-001", "foundation/atlas-001", "#30 vs #28")
