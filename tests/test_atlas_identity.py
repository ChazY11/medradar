"""ATLAS identity tests: the rules that stop name matching becoming identity.

These are offline tests.  They encode the specific mistakes the pilot must not
make, so a future refactor cannot quietly reintroduce them.
"""

from __future__ import annotations

import unittest

from medradar.atlas.identity import (
    CompanyIndex,
    DeviceView,
    compare_devices,
    normalize_di,
    normalize_name,
    normalize_regulatory_number,
)
from medradar.atlas.identity.resolver import (
    CONFIRMED,
    REJECTED,
    SAME_DEVICE_IDENTITY,
    SAME_MODEL,
    SAME_PRODUCT_FAMILY,
    UNRELATED,
    baseline_name_match,
)


def view(**kwargs) -> DeviceView:
    defaults = dict(
        ref=kwargs.pop("ref", "ref-1"),
        source_id=kwargs.pop("source_id", "source"),
        evidence_id=kwargs.pop("evidence_id", "ev-1"),
        firm_key=kwargs.pop("firm_key", ""),
        company_raw=kwargs.pop("company_raw", ""),
        brand=kwargs.pop("brand", ""),
        model=kwargs.pop("model", ""),
        product_codes=tuple(kwargs.pop("product_codes", ())),
        di=kwargs.pop("di", ""),
        identifiers=tuple(kwargs.pop("identifiers", ())),
    )
    return DeviceView(**defaults, **kwargs)


class NormalisationTests(unittest.TestCase):
    def test_di_keeps_leading_zeros(self) -> None:
        self.assertEqual(normalize_di(" 0871-7648-200274 "), "08717648200274")

    def test_510k_is_case_insensitive(self) -> None:
        self.assertEqual(normalize_regulatory_number("k123456"), "K123456")

    def test_company_name_folds_diacritics_and_suffixes(self) -> None:
        self.assertEqual(normalize_name("Drägerwerk AG & Co. KGaA"), "DRAEGERWERK AG AND CO KGAA")
        self.assertEqual(normalize_name("Medtronic, Inc."), "MEDTRONIC")

    def test_company_negative_guard_demotes_to_candidate(self) -> None:
        index = CompanyIndex.from_config()
        result = index.resolve("Philips Lighting B.V.")
        self.assertEqual(result["method"], "candidate")
        self.assertEqual(result["firm_key"], "philips")
        self.assertIn("negative_guard", result)

    def test_legacy_manufacturer_name_resolves_to_group(self) -> None:
        index = CompanyIndex.from_config()
        result = index.resolve("MEDTRONIC SOFAMOR DANEK, INC.")
        self.assertEqual(result["method"], "exact_alias")
        self.assertEqual(result["firm_key"], "medtronic")

    def test_unrelated_name_is_none_not_nearest(self) -> None:
        index = CompanyIndex.from_config()
        self.assertEqual(index.resolve("ACME STENT WORKS")["method"], "none")


class DeviceDecisionTests(unittest.TestCase):
    def test_shared_di_is_confirmed_identity(self) -> None:
        left = view(ref="a", di="08717648200274", brand="XIENCE ALPINE", model="1145350-28")
        right = view(ref="b", di="08717648200274", brand="XIENCE ALPINE", model="1145350-28")
        decision = compare_devices(left, right)
        self.assertEqual(decision.relation_type, SAME_DEVICE_IDENTITY)
        self.assertEqual(decision.status, CONFIRMED)
        self.assertEqual(decision.authority, "source_declared")

    def test_shared_di_with_conflicting_model_is_candidate_not_confirmed(self) -> None:
        left = view(ref="a", di="00000000000001", brand="CAPTION AI", model="AI")
        right = view(ref="b", di="00000000000001", brand="AMSCO 400", model="AMSCO 400")
        decision = compare_devices(left, right)
        self.assertEqual(decision.status, "CANDIDATE")
        self.assertTrue(decision.contradictions)
        self.assertIn("identifier agrees", decision.rejection_reason)

    def test_same_model_same_firm_is_not_device_identity(self) -> None:
        left = view(ref="a", firm_key="medtronic", model="X-1", di="11111111111111")
        right = view(ref="b", firm_key="medtronic", model="X-1", di="22222222222222")
        decision = compare_devices(left, right)
        self.assertEqual(decision.relation_type, SAME_MODEL)
        self.assertEqual(decision.status, CONFIRMED)
        self.assertNotEqual(decision.relation_type, SAME_DEVICE_IDENTITY)

    def test_shared_510k_is_family_not_device(self) -> None:
        left = view(ref="a", identifiers=(("510k", "K123456"),), model="A")
        right = view(ref="b", identifiers=(("510k", "K123456"),), model="B")
        decision = compare_devices(left, right)
        self.assertEqual(decision.relation_type, SAME_PRODUCT_FAMILY)
        self.assertNotEqual(decision.relation_type, SAME_DEVICE_IDENTITY)

    def test_identical_brand_across_companies_is_rejected(self) -> None:
        left = view(ref="a", firm_key="medtronic", brand="CONTROL", di="11111111111111")
        right = view(ref="b", firm_key="philips", brand="CONTROL", di="22222222222222")
        decision = compare_devices(left, right)
        self.assertEqual(decision.relation_type, UNRELATED)
        self.assertEqual(decision.status, REJECTED)
        self.assertIn("brand strings are not identities", decision.rejection_reason)

    def test_same_company_disjoint_product_codes_is_rejected(self) -> None:
        left = view(ref="a", firm_key="medtronic", product_codes=("NIQ",), di="11111111111111")
        right = view(ref="b", firm_key="medtronic", product_codes=("JAK",), di="22222222222222")
        decision = compare_devices(left, right)
        self.assertEqual(decision.relation_type, UNRELATED)
        self.assertEqual(decision.status, REJECTED)

    def test_shared_product_code_across_companies_is_technology_not_identity(self) -> None:
        left = view(ref="a", firm_key="medtronic", product_codes=("NIQ",), di="11111111111111")
        right = view(ref="b", firm_key="philips", product_codes=("NIQ",), di="22222222222222")
        decision = compare_devices(left, right)
        self.assertEqual(decision.relation_type, "RELATED_TECHNOLOGY")
        self.assertEqual(decision.status, "CANDIDATE")

    def test_shared_brand_token_across_firms_is_only_a_candidate(self) -> None:
        left = view(ref="a", firm_key="medtronic", brand="CARDIAC CONTROL SYSTEM")
        right = view(ref="b", firm_key="philips", brand="CARDIAC MONITOR")
        decision = compare_devices(left, right)
        self.assertEqual(decision.relation_type, "POSSIBLE_MATCH")
        self.assertEqual(decision.status, "CANDIDATE")
        self.assertEqual(decision.authority, "inferred")

    def test_no_identifier_and_no_shared_fields_is_unknown(self) -> None:
        left = view(ref="a", brand="ALPHA")
        right = view(ref="b", brand="OMEGA")
        decision = compare_devices(left, right)
        self.assertEqual(decision.relation_type, "UNKNOWN")
        self.assertEqual(decision.status, "UNKNOWN")

    def test_name_baseline_is_fooled_by_brand_collision(self) -> None:
        left = view(ref="a", firm_key="medtronic", brand="CONTROL", di="11111111111111")
        right = view(ref="b", firm_key="philips", brand="CONTROL", di="22222222222222")
        self.assertTrue(baseline_name_match(left, right))
        self.assertEqual(compare_devices(left, right).status, REJECTED)


class SafetyPropertyTests(unittest.TestCase):
    def test_candidate_never_marked_confirmed_by_comparison(self) -> None:
        """A model/name similarity may not produce SAME_DEVICE_IDENTITY."""
        for brand in ("XIENCE", "CONTROL", "CAPTION"):
            left = view(ref="a", brand=brand, model="M1", firm_key="medtronic")
            right = view(ref="b", brand=brand, model="M1", firm_key="philips")
            decision = compare_devices(left, right)
            self.assertNotEqual(decision.relation_type, SAME_DEVICE_IDENTITY)

    def test_all_decisions_carry_an_authority(self) -> None:
        pairs = [
            (view(ref="a", di="1" * 14), view(ref="b", di="1" * 14)),
            (view(ref="a", brand="X"), view(ref="b", brand="Y")),
        ]
        for left, right in pairs:
            decision = compare_devices(left, right)
            self.assertIn(decision.authority, {"source_declared", "derived", "inferred"})


if __name__ == "__main__":
    unittest.main()
