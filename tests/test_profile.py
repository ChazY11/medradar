"""Tests for the company technology profile engine (Understand layer)."""
from __future__ import annotations

import copy
import json
import unittest

from medradar.intelligence.profile import (
    MATERIAL_MONTHS,
    SEVEN_FIELDS,
    build_profile,
    render_markdown,
    validate_profile,
    _month_labels,
)

WINDOW = ("2020-01", "2023-12")   # 48 months, enough for momentum


def _events(spec):
    """spec: {track: [YYYY-MM, ...]} -> event dicts with a synthetic code."""
    events = []
    for track, months in spec.items():
        for month in months:
            events.append({"track": track, "date": f"{month}-15",
                           "code": f"C-{track}"})
    return events


def _profile(events, *, trials=(), codes=None, aliases=("ACME MEDICAL",),
             entities=("acme-medical-0000",), window=WINDOW):
    return build_profile(
        company_key="acme", display_name="Acme Medical", aliases=aliases,
        entity_keys=entities, as_of="2026-11-02", window=window,
        sources=("lane.sqlite",), regulatory_events=events,
        trial_events=list(trials), code_first_seen=codes,
    )


class SevenFieldsTest(unittest.TestCase):
    def test_exactly_seven_fields_in_order(self):
        self.assertEqual(len(SEVEN_FIELDS), 7)
        self.assertEqual(SEVEN_FIELDS[0], "identity")
        self.assertEqual(SEVEN_FIELDS[-1], "limits_and_provenance")

    def test_profile_contains_all_seven(self):
        profile = _profile(_events({"cardiac": ["2021-01", "2021-02"]}))
        for field in SEVEN_FIELDS:
            self.assertIn(field, profile)

    def test_profile_is_json_serialisable(self):
        profile = _profile(_events({"cardiac": ["2021-01"]}))
        self.assertIsInstance(json.dumps(profile), str)

    def test_schema_is_stamped(self):
        profile = _profile(_events({"cardiac": ["2021-01"]}))
        self.assertEqual(profile["schema"], "profile_v1")
        self.assertEqual(list(profile["fields"]), list(SEVEN_FIELDS))


class ValidationTest(unittest.TestCase):
    def test_valid_profile_has_no_problems(self):
        profile = _profile(_events({"cardiac": ["2021-01", "2022-01"]}))
        self.assertEqual(validate_profile(profile), [])

    def test_missing_field_is_reported(self):
        profile = _profile(_events({"cardiac": ["2021-01"]}))
        broken = copy.deepcopy(profile)
        del broken["concentration"]
        self.assertTrue(any("concentration" in problem
                            for problem in validate_profile(broken)))

    def test_contradictory_evidence_requires_checks(self):
        profile = _profile(_events({"cardiac": ["2021-01"]}))
        broken = copy.deepcopy(profile)
        broken["contradictory_evidence"]["checks"] = []
        self.assertTrue(any("checks" in problem for problem in validate_profile(broken)))

    def test_contradictory_evidence_requires_findings_key(self):
        profile = _profile(_events({"cardiac": ["2021-01"]}))
        broken = copy.deepcopy(profile)
        del broken["contradictory_evidence"]["found"]
        self.assertTrue(any("findings" in problem for problem in validate_profile(broken)))

    def test_render_refuses_invalid_profile(self):
        broken = {"schema": "profile_v1", "fields": list(SEVEN_FIELDS)}
        with self.assertRaises(ValueError):
            render_markdown(broken)


class MomentumTest(unittest.TestCase):
    def test_increasing(self):
        # 1 event in the prior 24 months, 6 in the last 24
        events = _events({"cardiac": ["2021-06", "2022-06",
                                      "2022-09", "2022-10", "2022-11", "2022-12",
                                      "2023-01", "2023-02"]})
        profile = _profile(events)
        self.assertEqual(profile["momentum"]["direction"], "increasing")
        self.assertEqual(profile["momentum"]["status"], "estimated")

    def test_decreasing(self):
        events = _events({"cardiac": ["2020-02", "2020-03", "2020-04", "2020-05",
                                      "2021-02", "2023-10"]})
        profile = _profile(events)
        self.assertEqual(profile["momentum"]["direction"], "decreasing")

    def test_stable(self):
        events = _events({"cardiac": ["2021-01", "2021-02", "2021-03", "2023-01",
                                      "2023-02", "2023-03"]})
        profile = _profile(events)
        self.assertEqual(profile["momentum"]["direction"], "stable")

    def test_insufficient_window(self):
        profile = _profile(_events({"cardiac": ["2021-01"]}),
                           window=("2023-01", "2023-12"))
        self.assertEqual(profile["momentum"]["status"], "insufficient_window")

    def test_no_prior_activity_is_undefined(self):
        events = _events({"cardiac": ["2023-01", "2023-02"]})
        profile = _profile(events)
        self.assertEqual(profile["momentum"]["direction"], "undefined")

    def test_statement_matches_numbers(self):
        events = _events({"cardiac": ["2021-01", "2021-02", "2023-01"]})
        momentum = _profile(events)["momentum"]
        self.assertIn(str(momentum["recent"]), momentum["statement"])
        self.assertIn(str(momentum["prior"]), momentum["statement"])


class ConcentrationTest(unittest.TestCase):
    def test_single_track_is_highly_concentrated(self):
        profile = _profile(_events({"cardiac": ["2021-01", "2021-02", "2021-03"]}))
        self.assertEqual(profile["concentration"]["label"], "highly concentrated")
        self.assertAlmostEqual(profile["concentration"]["hhi"], 1.0)

    def test_spread_tracks_are_diversified(self):
        spec = {f"track{i}": ["2021-01", "2021-02"] for i in range(8)}
        profile = _profile(_events(spec))
        self.assertEqual(profile["concentration"]["label"], "diversified")

    def test_no_events_is_handled(self):
        profile = _profile([])
        self.assertEqual(profile["concentration"]["status"], "no_events")
        self.assertIsNone(profile["concentration"]["hhi"])


class ContradictoryEvidenceTest(unittest.TestCase):
    def test_checks_always_listed(self):
        profile = _profile(_events({"cardiac": ["2021-01"]}))
        self.assertGreaterEqual(len(profile["contradictory_evidence"]["checks"]), 4)

    def test_sparse_months_flagged(self):
        profile = _profile(_events({"cardiac": ["2021-01", "2022-01"]}))
        checks = {item["check"] for item in profile["contradictory_evidence"]["found"]}
        self.assertIn("sparse_months", checks)

    def test_single_event_track_flagged(self):
        profile = _profile(_events({"cardiac": ["2021-01", "2021-02"],
                                    "once": ["2022-05"]}))
        checks = {item["check"] for item in profile["contradictory_evidence"]["found"]}
        self.assertIn("single_event_tracks", checks)

    def test_decline_flagged(self):
        events = _events({"cardiac": ["2020-02", "2020-03", "2020-04", "2020-05",
                                      "2021-02", "2023-01"]})
        profile = _profile(events)
        checks = {item["check"] for item in profile["contradictory_evidence"]["found"]}
        self.assertIn("activity_decline_by_track", checks)

    def test_churn_exposure_flagged(self):
        codes = {"C-cardiac": "2023-06"}
        events = _events({"cardiac": [f"2023-{month:02d}" for month in range(1, 7)]})
        profile = _profile(events, codes=codes)
        checks = {item["check"] for item in profile["contradictory_evidence"]["found"]}
        self.assertIn("taxonomy_churn_exposure", checks)

    def test_no_findings_reports_zero_not_omission(self):
        # dense activity in every month across the window, three tracks, no code map:
        # nothing should be flagged, and the field must still say so explicitly
        months = [f"{year}-{month:02d}" for year in range(2020, 2024) for month in range(1, 13)]
        events = _events({f"track{i}": months for i in range(3)})
        profile = _profile(events)
        self.assertEqual(profile["contradictory_evidence"]["found"], [])
        self.assertIn("no contradictory observation", profile["contradictory_evidence"]["statement"])


class FootprintAndCorroborationTest(unittest.TestCase):
    def test_single_event_track_marked_insufficient(self):
        profile = _profile(_events({"cardiac": ["2021-01", "2021-02"],
                                    "once": ["2022-05"]}))
        rows = {row["track"]: row for row in profile["technology_footprint"]["rows"]}
        self.assertTrue(rows["cardiac"]["sufficient_evidence"])
        self.assertFalse(rows["once"]["sufficient_evidence"])

    def test_corroboration_splits_by_trial_support(self):
        events = _events({"cardiac": ["2021-01"], "neuro": ["2021-02"]})
        trials = _events({"cardiac": ["2021-03"]})
        result = _profile(events, trials=trials)["independent_corroboration"]
        self.assertEqual(result["tracks_with_trial_support"], ["cardiac"])
        self.assertEqual(result["tracks_without_trial_support"], ["neuro"])

    def test_no_trials_means_no_support(self):
        result = _profile(_events({"cardiac": ["2021-01"]}))["independent_corroboration"]
        self.assertEqual(result["tracks_with_trial_support"], [])
        self.assertEqual(result["trial_events"], 0)


class RenderTest(unittest.TestCase):
    def test_all_seven_sections_present(self):
        markdown = render_markdown(_profile(_events({"cardiac": ["2021-01"]})))
        for heading in ("## 1. Identity", "## 2. Technology footprint", "## 3. Momentum",
                        "## 4. Concentration", "## 5. Independent corroboration",
                        "## 6. Contradictory evidence", "## 7. Limits and provenance"):
            self.assertIn(heading, markdown)

    def test_markdown_states_as_of_and_sources(self):
        markdown = render_markdown(_profile(_events({"cardiac": ["2021-01"]})))
        self.assertIn("As of 2026-11-02", markdown)
        self.assertIn("lane.sqlite", markdown)

    def test_markdown_lists_contradictions(self):
        markdown = render_markdown(_profile(_events({"cardiac": ["2021-01", "2022-01"]})))
        self.assertIn("sparse_months", markdown)

    def test_markdown_is_deterministic(self):
        events = _events({"cardiac": ["2021-01", "2022-02"]})
        self.assertEqual(render_markdown(_profile(events)), render_markdown(_profile(events)))


class MonthLabelTest(unittest.TestCase):
    def test_inclusive_and_crosses_years(self):
        self.assertEqual(_month_labels("2020-11", "2021-02"),
                         ["2020-11", "2020-12", "2021-01", "2021-02"])

    def test_single_month(self):
        self.assertEqual(_month_labels("2020-05", "2020-05"), ["2020-05"])


class DeterminismTest(unittest.TestCase):
    def test_identical_inputs_give_identical_profiles(self):
        events = _events({"cardiac": ["2021-01", "2022-01"], "neuro": ["2021-05"]})
        first = json.dumps(_profile(events), sort_keys=True)
        second = json.dumps(_profile(events), sort_keys=True)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
