"""Build a module dependency matrix for a git ref of the MedRadar repo.

Parses ``from .x import`` / ``from medradar.x import`` / ``import medradar.x``
statements (relative imports resolved per module path) and renders a coarse
package-level matrix. Read-only: only `git show`/`git ls-tree` are used.
"""
import collections
import re
import subprocess
import sys

GIT = ["git", "-C", r"<REDACTED_LOCAL_PATH>"]
PKGS = ["__main__", "analyze", "audit", "calibration", "cases", "clinical", "collect_device",
        "collect_drug", "config", "corpus", "dashboard", "db", "eventstudy", "families",
        "forecast_registry", "frontier", "http", "intelligence", "live", "llm", "nmpa",
        "onboarding", "paper", "prices", "products", "replay", "report", "research_agent",
        "stats", "stats_cmd", "studies", "tkg", "util", "adcom", "products", "cases"]
ALIAS = {"__main__": "cli", "collect_device": "collectors", "collect_drug": "collectors",
         "clinical": "collectors", "adcom": "collectors", "nmpa": "collectors",
         "analyze": "analysis", "eventstudy": "analysis", "paper": "analysis", "replay": "analysis",
         "report": "render", "dashboard": "render", "stats_cmd": "render", "stats": "render",
         "research_agent": "analysis", "calibration": "intelligence", "families": "analysis",
         "products": "analysis", "cases": "analysis", "corpus": "analysis", "frontier": "analysis",
         "onboarding": "cli", "live": "analysis", "llm": "analysis", "prices": "collectors",
         "http": "collectors", "util": "lib", "db": "storage", "config": "lib",
         "forecast_registry": "storage", "tkg": "storage", "intelligence": "intelligence",
         "studies": "studies", "audit": "analysis"}


def run(*args):
    return subprocess.run(GIT + list(args), capture_output=True, text=True, errors="replace").stdout


def pkg_of(path):
    parts = path.split("/")
    if parts[0] != "medradar":
        return None
    if len(parts) == 2:
        return ALIAS.get(parts[1].removesuffix(".py"), "lib")
    return ALIAS.get(parts[1], parts[1])


def main(ref="origin/main", scope="medradar"):
    files = [p for p in run("ls-tree", "-r", "--name-only", ref, "--", scope).splitlines() if p.endswith(".py")]
    edges = collections.Counter()
    detail = collections.defaultdict(set)
    for f in files:
        src = run("show", f"{ref}:{f}")
        src_pkg = pkg_of(f)
        # dotted module path of this file, e.g. medradar.intelligence.pipeline
        this_mod = f[:-3].replace("/", ".")
        this_pkg = ".".join(this_mod.split(".")[:-1])
        for line in src.splitlines():
            m = re.match(r"\s*from\s+(\.+)([\w.]*)\s+import", line)
            if m:
                dots, rest = m.group(1), m.group(2)
                if not rest:
                    continue
                base = this_pkg.split(".")
                # level 1 = current package, level n = n-1 parents up
                if dots != ".":
                    base = base[: len(base) - (len(dots) - 1)]
                target = ".".join(base + rest.split("."))
                tp = pkg_of(target.replace(".", "/") + "/x.py")
                if tp and tp != src_pkg:
                    edges[(src_pkg, tp)] += 1
                    detail[(src_pkg, tp)].add(f)
                continue
            m = re.match(r"\s*from\s+(medradar[\w.]*)\s+import", line)
            if m:
                tp = pkg_of(m.group(1).replace(".", "/") + "/x.py")
                if tp and tp != src_pkg:
                    edges[(src_pkg, tp)] += 1
                    detail[(src_pkg, tp)].add(f)
    pkgs = sorted({a for a, _ in edges} | {b for _, b in edges})
    print("files:", len(files), "edges:", len(edges))
    print("\nFROM\\TO " + " ".join(f"{p:^12s}" for p in pkgs))
    for a in pkgs:
        row = [f"{edges.get((a,b),0):^12d}" for b in pkgs]
        print(f"{a:14s}" + " ".join(row))
    print("\nEdges (count, files):")
    for (a, b), n in edges.most_common():
        print(f"  {a:14s} -> {b:14s} {n:4d}  {sorted(detail[(a,b)])[:3]}")


if __name__ == "__main__":
    main(*(sys.argv[1:] or []))
