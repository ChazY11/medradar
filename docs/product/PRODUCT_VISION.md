# MedRadar - Product Vision

**MedRadar - Medical Technology Intelligence Platform**
Chinese: **MedRadar 医疗技术情报与竞争分析平台**

Status: PRODUCT-001 delivered a working v1 workbench. This document states the product this
repository is now being built for, and what the v1 does and does not deliver.

---

## 1. The problem

A competitive-intelligence analyst at a medical device company, or a product manager preparing a
market entry, needs to answer questions like:

* What has this competitor actually filed with the FDA recently, and what changed?
* How does its regulatory activity compare with another company's, given that both operate through
  a web of subsidiaries and applicant names?
* Which of these claims can I defend in an internal review, and where is the primary source?

Today that work is manual: FDA databases are queryable but not organised around a company,
applicant names do not match legal entities, "event date" and "when this became public" are
different facts, and the comparison you build is only as trustworthy as the caveats you remember
to attach.

MedRadar's bet is that the missing product is **not more data and not more AI prose**. It is a
workbench where every number is a count of real regulatory records, every record is attributed by
a reviewed rule, every claim links to the official source, and the limits are printed next to the
numbers instead of being hidden in a methodology appendix.

## 2. Target users

| User | Job to be done | What they need from MedRadar |
|---|---|---|
| Strategy analyst (device company) | Monitor and compare competitors | Company view, recent regulatory activity, side-by-side comparison, exportable evidence |
| Product manager | Understand a technology area and who is active in it | Activity by FDA medical specialty, comparable windows, record-level evidence |
| International / market-access lead | Reason about a non-US parent and its US activity | Honest identity handling (applicant names vs legal entities), coverage limits |
| Competitive-intelligence researcher | Produce a defensible brief | Traceable sources, explicit time semantics, warnings where data is not comparable |
| Founder / investor researcher | Fast orientation on a company | Search, coverage summary, recent records, what is unknown |

The primary acceptance persona is a **competitive-intelligence analyst** who must
compare two medical-technology companies and hand a sourced summary to someone else.

## 3. Product capabilities (long-term)

| # | Capability | PRODUCT-001 status |
|---|---|---|
| A | **Company Intelligence** - what a company is doing across products and regulation | **Delivered for FDA device records**: organization profile, coverage, activity distribution, recent records, attribution audit |
| B | **Regulatory Intelligence** - search and analyse FDA regulatory records and changes | **Delivered**: 510(k), PMA (originals and supplements), recalls; filter, sort, evidence drawer |
| C | **Competitive Intelligence** - compare companies on explicit, identical measures | **Delivered**: 2-4 organizations, one window, one counting rule, coverage and pathway-mix warnings |
| D | **Evidence Research** - go from an analysis to the primary record and cite it | **Delivered**: official identifier, official FDA URL, verbatim source fields, snapshot provenance, CSV and Markdown export |
| E | **Monitoring** - continuously track new public information | **Not delivered in v1**. The system is explicitly snapshot-based; the observatory prototypes exist in draft branches and are the basis for the next phase. |

## 4. What v1 is

A single-process web application:

* a curated snapshot of **91,457 FDA device records** (510(k), PMA, recalls) for **59 tracked
  organizations**, collected from openFDA on 2026-11-14/15 and committed to the repository;
* an identity layer that maps **1,590 verbatim applicant spellings** to those organizations by
  exact, reviewed rules, with 9 explicitly rejected look-alike names;
* a FastAPI JSON layer and a React workbench with six screens;
* CSV and Markdown exports that reproduce exactly what the screen shows, with source links and
  provenance.

## 5. What v1 is not

* Not a live feed, not real-time, not a monitoring service.
* Not a ranking of companies by innovation, quality or market share.
* Not a complete FDA applicant registry: 59 tracked organizations, with unattributed strings
  published in the audit rather than hidden.
* Not an AI product: there is no generated narrative anywhere in the product. Every sentence about
  data is derived from the records or is an explicit methodological statement.
* Not a replacement for the research programme in this repository: the science modules and their
  frozen results are untouched.

## 6. Product principles (binding)

1. **Evidence before AI.** AI may help build and review the pipeline; it is never the source of a
   fact shown to a user.
2. **A number is only shown with its basis and coverage.** No bare counts, no implied "more
   activity = better".
3. **Identity decisions are reviewable.** Exact string matching, explicit accept/reject lists,
   documented provenance, provisional status shown in the UI.
4. **Four times, never one.** Event date, source publication date, first observed by MedRadar and
   available-at are separate fields with separate meanings.
5. **Gaps are part of the product.** Out-of-scope sources, unattributed records and stale snapshots
   are shown, not smoothed away.
6. **Small enough for one maintainer.** One Python process, one read-only snapshot, one built
   frontend, zero paid infrastructure.

## 7. How success is judged

Short term (this release):

* a new developer can start the product from the repository and complete the analyst workflow
  (search -> organization -> records -> evidence -> compare -> export) in under ten minutes;
* every number on screen is reproducible from the committed snapshot and the API;
* the acceptance walkthrough passes in a real browser (see `docs/product/ACCEPTANCE.md`).

Medium term:

* the provisional-attribution share falls and a human review workflow exists;
* product-level identities (a device, not a record) are modelled;
* a scheduled collection process replaces the manual snapshot, with the same audit trail.

Long term:

* MedRadar answers "what is this company doing and how does it compare" faster and more
  defensibly than manual FDA searching, while remaining honest about what public FDA data can
  and cannot prove.
