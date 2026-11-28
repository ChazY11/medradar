# Public tunnel: reconnect window and start limit

Measured 2026-11-28, during round 91.

## What happened

A public check returned **502 on three pages in a row** while `127.0.0.1:8791` answered 200. The tunnel unit
was active; the journal showed two reconnects at the same second. localhost.run rotates its subdomain and
the ssh session re-establishes, and during that gap the relay answers 502 for the old address.

Sampled hourly-ish afterwards: **24 samples over 4 minutes, 24 × 200** (median 1.18 s, min 1.00 s). The 502
was a reconnect blip, not a broken tunnel. The stale-looking `public_url.txt` was already correct — the
script rewrites it on every reconnect.

## What was controllable

The unit had `RestartSec=15` and no start-limit override, so:

* a dropped session meant **up to 15 s of 502**;
* a burst of reconnects could exhaust systemd's default start limit and leave the unit stopped.

Changed:

```
StartLimitIntervalSec=0     # a burst of reconnects must not stop the unit for good
RestartSec=2                # was 15
```

## Measured after

Restarted the unit and probed once a second:

```
恢复：5 秒（第 3 次探测）
新地址：https://2e3fbbc20bf1f1.app.lhr.life
```

Then all five representative pages, through the new address, with the alpha gate:

```
/ 1.37s · /area?name=Dental 3.14s · /areas?sort=recent 5.57s · /paper?id=… 2.03s · /device?query=K213506 6.39s
401 without credentials · failed units 0
```

The 3–6 s figures are the first requests on a fresh connection to a newly rotated address; later samples in
the same session were 1.0–1.2 s. Recorded here rather than smoothed away, because a reader's first click
after a rotation is exactly what these numbers describe.

## Still true

* The address **rotates**; only a custom domain on a paid plan fixes that, and none is available here.
* A reconnect still costs a few seconds of 502 — now bounded by 2 s, not 15 s.
* Nothing else in the stack advertises the old address: the file is rewritten by the same loop that prints it.
---
# A reconnect storm is worse than a slow reconnect

Measured 2026-11-28, end of round 101.

## What happened

Public checks returned `000` on three pages in a row while the local service answered 200 in 0.46 s. The
tunnel unit was active with **17 restarts**, and its log said:

```
18:14:55 ssh: connect to host localhost.run port 22: Connection refused
18:14:55 Deactivated successfully.
18:14:57 Scheduled restart job, restart counter is at 17.
```

So the relay briefly refused us, and `RestartSec=2` - installed in round 91 to shorten the 502 window -
turned that into a reconnect every two seconds. The service looked broken while it was mostly us retrying
too hard.

A manual connection minutes later reached the welcome banner, and the next address answered 200 three times
in a row. The relay was fine; the storm was ours.

## What changed

```
RestartSec=5  RestartSteps=4  RestartMaxDelaySec=60   # five seconds, doubling to a minute
StartLimitIntervalSec=0                              # one outage must not stop the unit for good
```

This trades a few seconds of extra 502 window (round 91 wanted 2 s) for not provoking the relay during an
outage. Measured after: restarts 0, address serving 200 in 0.88-1.04 s, gate 401, no failed units.

## The lesson for this file

Round 91 optimised the reconnect window without measuring what repeated reconnects do to the other end. Both
numbers are now written down: a single reconnect costs a few seconds of 502, and a burst costs the tunnel for
minutes.
