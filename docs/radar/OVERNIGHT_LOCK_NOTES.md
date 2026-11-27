# Two runs at once, and a guard that did not verify

Round 57. This note exists because a mechanism I tried to add did not work, and the honest record is
worth more than a clean-sounding commit.

## What happened

The scheduled nightly run fired at 04:31 local on 2026-11-28 and completed all eleven steps
unattended — patent attempts exactly 600 s apart, ledger rows from 04:31:26 to 04:55:36. That is the
first real execution of the chain, and it is the evidence round 43 was waiting for.

But it recorded **one** paper field, not three:

```
_paper: Medical Genetics  stored 97
```

Not a scripting bug. A manual backfill I started at 04:46 had already crawled the fields the scheduled
run would have picked, so by 04:52 only one never-run field remained and `next_queries(count=3)` had
one thing to return. The picks/read loop was re-tested afterwards and reads three tab-separated lines
correctly under `dash`.

## What that exposed

Two crawlers can run at the same time. Nothing was corrupted, but the ledger became unexplainable
without reading my own shell history — which is not a record.

## What I tried, and what happened

A lock, so the second runner says so instead of silently interleaving.

Attempt 1 used `flock -n` on an inherited descriptor. Run by hand, the same four lines block. Inside the
deployed script, they did not: the second run proceeded straight to `preprint pass`. Attempt 2 used an
exclusive create (`set -C`) with a pid + `kill -0` staleness check — the same code blocks when run by
hand, and the same code did not block in the script.

I did not find the difference before the budget ran out, and a guard that works only when tested by hand
is worse than no guard: it would be trusted.

**Reverted.** `deploy/preprint_nightly.sh` is back to its previously committed state.

## What the investigation did surface

While testing, several runs were left alive by `timeout` (the shell does not exit while a child holds
on), and each run's `trap 'rm -rf "$WORK"'` began deleting work directories that another run had just
created — visible as:

```
cannot create /tmp/medradar-nightly.Jhd8F2/step_patents_1.log: Directory nonexistent
```

So the cost of concurrent runs is worse than "one field instead of three": work directories get pulled
out from under a live run. That raises the priority of the lock rather than lowering it.

After killing every run and clearing `/tmp`, a single clean run started normally:

```
[2026-11-28T06:45:42+08:00] preprint pass
  "stored": 0, "skipped_cached": 61,
```

with no `cannot create` or `Permission denied` lines.

## Next attempt should start here

The difference between the hand-run snippet and the deployed script is not the lock code — it is the
environment the script runs in. Check, in order:

1. whether `$LOCK` expands to the same path under `dash` when `MEDRADAR_RADAR_DIR` is set (print it);
2. whether `set -u` plus a command substitution makes the `if` condition evaluate in a subshell;
3. whether the script's own `trap ... EXIT INT TERM` interacts with the guard.

Print the decision unconditionally (`echo "lock: held=$HELD alive=$(kill -0 ...)"`) in a test build and
compare against the same lines typed by hand.
