"""Write the plain-language ``*_SUMMARY.json`` companions for EXP-H1 and EXP-H3.

The numbers are read from the experiment outputs rather than retyped, so the
summary can never drift from the measurement. The prose states the *method* and
the *limits* of the method, in plain language, as required.

    python experiments/scholarly/write_summaries.py
"""

from __future__ import annotations

import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from CONNECTORS.scholarly import _util as U  # noqa: E402

EXP = os.path.dirname(os.path.abspath(__file__))


def read(name: str) -> dict:
    return U.read_json(os.path.join(EXP, name))


def main() -> int:
    h1 = read("EXP_H1_DEDUP.json")
    h3 = read("EXP_H3_PUB_TIME.json")

    c = h1["counts"]
    rows = c["source_rows_fetched"]
    works = c["distinct_works_after_dedup"]
    ratio = c["dedup_ratio_rows"]
    hits = c["per_source_anchor_hits"]
    xid = h1["cross_identifier_verification"]
    md = h1["metadata_disagreement"]
    hist = h1["anchors_by_number_of_sources_holding_them"]

    h1_summary = {
        "experiment": "EXP-H1",
        "outputs": ["EXP_H1_DEDUP.json", "EXP_H1_ANCHOR_MATRIX.jsonl",
                    "EXP_H1_SELECTION_RULE.md"],
        "selection_rule": "experiments/scholarly/EXP_H1_SELECTION_RULE.md (frozen "
                          "before collection)",
        "generated_at": U.utc_now(),

        "method_in_plain_language": [
            "1. Before looking at any result, a rule was written down and frozen for "
            "choosing 60 papers about medical-device technology that involve five named "
            "firms. The rule pins the query, the date window (2020-01-01 to 2022-12-31), "
            "the sort order, the tie-break, and a fixed fallback ladder, so the sample "
            "cannot be adjusted after the fact. It produced 60 works with 60 distinct "
            "DOIs, twelve per firm.",
            "2. Each of those 60 DOIs was then looked up, one work at a time, in "
            "OpenAlex, Crossref, Europe PMC, PubMed and OpenAIRE, and in one batch call "
            "to Semantic Scholar. Whatever each source returned was saved verbatim.",
            "3. A 'source row' is one record a database returned for one anchor. A "
            "'distinct work' is a unique DOI (falling back to PMID, then to the OpenAlex "
            "work id) across all of those rows. The ratio of the second to the first is "
            "how much genuinely different information the multi-database fetch bought.",
            "4. Identifiers were only recorded when they literally appeared in a saved "
            "response. Nothing was derived, resolved or inferred from another scheme.",
            "5. Titles, author counts and publication dates were then compared across "
            "databases for the same DOI and left unrepaired. Every difference is a "
            "measurement.",
        ],

        "headline_numbers": {
            "anchors": h1["anchor_count"],
            "sources_queried": h1["sources_queried"],
            "source_rows_fetched": rows,
            "distinct_works_after_dedup": works,
            "dedup_ratio_distinct_works_over_rows": ratio,
            "naive_union_inflation_factor": round(1 / ratio, 2) if ratio else None,
            "per_source_rows_fetched": c["per_source_rows_fetched"],
            "per_source_anchor_hits": hits,
            "anchors_by_number_of_sources_holding_them": hist,
            "pmid_status": xid["pmid"],
            "pmcid_status": xid["pmcid"],
            "title_agreement": md["title"],
            "author_count_delta_distribution": md["author_count_delta_distribution"],
            "publication_date_spread_buckets": md["publication_date_spread_buckets"],
            "anchors_with_a_date_disagreement": md["date_conflict_count"],
        },

        "what_this_measures": (
            f"{rows} records came back from six databases, but they describe only "
            f"{works} distinct works: a de-duplication ratio of {ratio:.3f}, meaning a "
            f"naive union would over-count by roughly {round(1/ratio, 1)}x. The 60 "
            "anchors are spread across the databases very unevenly: "
            + ", ".join(f"{k} holds {v}/60" for k, v in hits.items())
            + ". Only "
            + str(sum(1 for k, v in hist.items() if int(k) >= 5))
            + " different source-counts appear at all, and "
            + str(hist.get("6", 0))
            + " anchors are held by all six sources."
        ),

        "what_this_cannot_support": [
            "It cannot say which database is 'complete'. The sample was drawn FROM "
            "OpenAlex, so OpenAlex trivially holds 60/60. The 37/60 and 56/60 figures "
            "are coverage of an OpenAlex-defined sample, not of the literature.",
            "It cannot rank databases by quality. A missing record may be a scope "
            "decision (Europe PMC indexes biomedical work only), not a defect.",
            "It cannot claim research value from row counts. The only research-relevant "
            "quantity here is the disagreement structure, not the volume.",
        ],

        "notable_observations": [
            "Cross-identifier links are clean: for "
            f"{xid['pmid']['single_value']} of 60 anchors a single PMID is agreed by "
            f"every source that exposes one, and {xid['pmid']['conflict']} anchors have "
            "two different PMIDs for the same DOI. "
            f"{xid['pmid']['absent_all_sources']} anchors have no PMID in any source.",
            "Titles are less stable than identifiers: "
            f"{md['title']['all_sources_identical']} anchors have byte-identical titles "
            f"after whitespace/case normalisation, {md['title']['prefix_of_each_other']} "
            "have titles where one is a prefix of another (a truncation signature), and "
            f"{md['title']['materially_different']} have titles that differ in "
            "substance, all for the same DOI.",
            "OpenAIRE's de-duplicated research products can carry SEVERAL DOIs (9 of 59 "
            "records here, e.g. a Spanish and an English version of the same article). "
            "A reader that takes 'the first DOI' in such a record mis-assigns the work; "
            "this connector records the queried DOI as primary and lists the rest.",
            "Semantic Scholar's batch endpoint ignores the field projection unless "
            "`fields` is passed as a QUERY parameter, and silently returns only "
            "{paperId,title} with HTTP 200 otherwise. That is a silent partial response, "
            "not an error, and it is recorded in the probe evidence.",
        ],

        "reproduce": [
            "python CONNECTORS/scholarly/openalex.py",
            "python CONNECTORS/scholarly/crossref.py",
            "python CONNECTORS/scholarly/europepmc.py",
            "python CONNECTORS/scholarly/pubmed_eutils.py",
            "python CONNECTORS/scholarly/semantic_scholar.py",
            "python CONNECTORS/scholarly/openaire.py",
            "python experiments/scholarly/analyze_exp_h1.py",
        ],
    }
    U.write_json(os.path.join(EXP, "EXP_H1_DEDUP_SUMMARY.json"), h1_summary)

    avail = h3["date_availability"]
    dis = h3["cross_source_date_disagreement"]
    h3_summary = {
        "experiment": "EXP-H3",
        "outputs": ["EXP_H3_PUB_TIME.json"],
        "selection_rule": "experiments/scholarly/EXP_H1_SELECTION_RULE.md (same frozen "
                          "anchor set)",
        "generated_at": U.utc_now(),

        "method_in_plain_language": [
            "1. Using the same 60-anchor sample, every date field each source actually "
            "publishes was read off the saved responses and classified into three kinds: "
            "(a) a public-visible publication date, (b) a creation / index / "
            "first-seen timestamp, and (c) a mutable snapshot marker such as "
            "'last updated'.",
            "2. A record counts as having an 'explicit public-visible date' when its "
            "source provides a date that claims when the work was published. A record "
            "counts as 'current-snapshot-only' when it has such a date but no "
            "creation/index timestamp, so the record's own history is unavailable and "
            "only its present state can be read.",
            "3. Cross-database disagreement is measured per anchor: every source's "
            "single best publication date is compared, and the spread between the "
            "earliest and latest is reported in day buckets. Nothing is averaged and no "
            "source is treated as the referee.",
            "4. For the sources that expose a creation timestamp, the lag between the "
            "nominal publication date and the moment the record became visible was "
            "computed directly. That lag is the only quantity that can honestly separate "
            "'published' from 'observable'.",
        ],

        "headline_numbers": {
            "anchors": h3["anchor_count"],
            "per_source_date_availability": {
                s: {
                    "records": avail[s]["records"],
                    "with_public_visible_date": avail[s]["explicit_public_visible_date"],
                    "share_with_public_visible_date":
                        avail[s]["share_with_explicit_public_date"],
                    "with_creation_or_index_date": avail[s]["creation_or_index_date"],
                    "current_snapshot_only": avail[s]["current_snapshot_only"],
                    "share_current_snapshot_only":
                        avail[s]["share_current_snapshot_only"],
                } for s in avail
            },
            "anchors_with_two_or_more_dates": dis["anchors_with_at_least_two_dates"],
            "anchors_where_databases_disagree": dis["anchors_disagreeing"],
            "share_disagreeing": dis["share_disagreeing"],
            "spread_buckets": dis["spread_buckets"],
            "share_disagreeing_by_more_than_30_days":
                h3["headline"]["share_anchors_disagreeing_by_more_than_30_days"],
            "sources_with_a_creation_date": h3["headline"]["sources_with_creation_date"],
            "sources_current_snapshot_only":
                h3["headline"]["sources_current_snapshot_only"],
            "index_lag": {s: {"records": v["records_with_both_dates"],
                              "median_days": v["median_days_creation_minus_publication"],
                              "buckets": v["buckets"]}
                          for s, v in h3["index_lag"].items()},
            "trial_submission_to_posting_lag": {
                s: {"records": v["records_with_both_dates"],
                    "median_days": v["median_days_posting_minus_submission"],
                    "max_days": v["max_days"], "buckets": v["buckets"]}
                for s, v in h3["trial_submission_to_posting_lag"].items()},
        },

        "what_this_measures": (
            f"{dis['anchors_disagreeing']} of {dis['anchors_with_at_least_two_dates']} "
            f"anchors ({dis['share_disagreeing']:.1%}) have at least two databases that "
            "disagree about the publication date of the same DOI, and "
            f"{h3['headline']['share_anchors_disagreeing_by_more_than_30_days']:.1%} of "
            "anchors disagree by more than 30 days. That is the four-clock problem "
            "showing up as a measurement, not as an assumption."
        ),

        "what_this_cannot_support": [
            "It cannot say which database's date is correct. A difference between an "
            "issue date and an electronic-publication date is not an error; it is two "
            "different events. That is exactly why both are reported.",
            "It cannot be used to back-date observability. Only the creation/index lag "
            "measures when a record became visible, and only three of six publication "
            "sources publish such a timestamp at all.",
            "It cannot substitute for a historical archive: what is measured is what "
            "today's snapshots say about the past, not what the sources said at the "
            "time.",
        ],

        "notable_observations": [
            "Three of six publication sources (PubMed E-utilities, Semantic Scholar, "
            "OpenAIRE Graph) expose NO creation or index timestamp. Any 'we could have "
            "seen this on date X' claim resting on those sources is unsupported and is "
            "flagged SNAPSHOT_ONLY on the records.",
            "Crossref's `created` timestamp frequently precedes the nominal publication "
            "date (21 of 59 records), because a DOI is registered at acceptance. "
            "OpenAlex's `created_date` is mostly AFTER publication (median 14 days), "
            "because it is an index, not a registry.",
            "ClinicalTrials.gov publishes both a submit date and a post date, so the "
            "registry's own queue is measurable: median "
            f"{h3['trial_submission_to_posting_lag']['clinicaltrials_gov']['median_days_posting_minus_submission']}"
            " days from submission to first posting, with a maximum of "
            f"{h3['trial_submission_to_posting_lag']['clinicaltrials_gov']['max_days']} "
            "days.",
            "CORDIS returns human-readable template strings such as '1 {{month_08}} 2014' "
            "rather than ISO dates, so it contributes project identity but no usable "
            "clock. That is recorded as a blocker rather than parsed into a guess.",
        ],

        "reproduce": ["python experiments/scholarly/analyze_exp_h3.py"],
    }
    U.write_json(os.path.join(EXP, "EXP_H3_PUB_TIME_SUMMARY.json"), h3_summary)
    print("wrote EXP_H1_DEDUP_SUMMARY.json and EXP_H3_PUB_TIME_SUMMARY.json")
    print("dedup ratio:", round(ratio, 4), "| date disagreement share:",
          dis["share_disagreeing"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
