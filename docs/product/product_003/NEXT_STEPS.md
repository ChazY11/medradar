# NEXT_STEPS

Ranked by user value per unit of work, based on what this release found.

## 1. Human/independent review of device relations (turns G2 from declared to measured)

The confirmed relations are 100% rule-derived from official identifiers, which is strong - but no
independent sample has checked whether the *interpretation* is right (for example whether a PMA
family is being read as one commercial device when the company treats the models as separate
products). The existing PRODUCT-002 review machinery (append-only ledger, loopback service, sample
protocol) can be reused for relation review: the sample design, rule and evidence format are already
modelled in `quality.py`.

## 2. Recall-to-device identity beyond the K-number field

28.8% of recalls have no official K reference. Two options with real evidence, in this order:
(a) collect the FDA recall record's product description and match it against UDI/GUDID labeler data
(needs its own governance review and a UDI source), or (b) keep them unlinked but let an analyst
record a reviewed link in the existing ledger. Guessing from product codes is explicitly rejected.

## 3. Device explorer as a working tool: saved filters, comparison and monitoring

The explorer now answers "which device is this". The next useful step is "show me what changed for
these devices since the last snapshot": a device-level diff (new clearances, new supplements, new
recalls) using the existing snapshot id and first-observed dates. That is the workflow an industry
analyst actually repeats weekly.

## Deliberately not next

* A prettier relationship graph: the evidence does not support dense device graphs, and a graph would
  encourage exactly the false lineage this release refuses to create.
* Cross-pathway "same device" inference: no official identifier exists; candidates already carry the
  honest label.
* Extending to global regulators before the FDA path is reviewed: it would multiply unverified
  identity claims instead of reducing them.
