"""Structured parameters out of 510(k) device descriptions.

What this is and what it is not
-------------------------------
A 510(k) Summary states what the manufacturer says the device is and how it works. When a summary
says "0.014 inch guidewire" or "120 mmHg", that is a **claim made in that document**, not a
verified engineering specification. Every parameter this module produces therefore carries:

* ``document`` - the K number it came from,
* ``sentence`` - the clause it was read out of, because a bare number is not a specification,
* ``assertion`` - literally ``"manufacturer_statement_in_510k_summary"``.

A reader must be able to see that provenance without asking. Summing these into a "spec sheet"
would be inventing a document the manufacturer never wrote.

Why the context is kept
-----------------------
Measured on the corpus: the same digits appear as a length, a diameter and a catalogue number in
adjacent sentences. "0.014" is a wire diameter in one clause and part of a list number in the next,
so a parameter without its sentence cannot be checked by anyone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

#: Unit -> (canonical unit, quantity). Only units that appear in device summaries are listed;
#: anything else is deliberately dropped rather than guessed at.
UNITS: dict[str, tuple[str, str]] = {
    # length
    "mm": ("mm", "length"), "millimeter": ("mm", "length"), "millimeters": ("mm", "length"),
    "cm": ("cm", "length"), "centimeter": ("cm", "length"), "centimeters": ("cm", "length"),
    "m": ("m", "length"), "inch": ("in", "length"), "inches": ("in", "length"),
    "in": ("in", "length"), "ft": ("ft", "length"), "feet": ("ft", "length"),
    # catheter and needle gauges
    "fr": ("Fr", "gauge"), "french": ("Fr", "gauge"),
    "g": ("ga", "gauge"), "ga": ("ga", "gauge"), "gauge": ("ga", "gauge"),
    # volume and flow
    "ml": ("mL", "volume"), "mℓ": ("mL", "volume"), "μl": ("µL", "volume"),
    "ul": ("µL", "volume"), "l": ("L", "volume"),
    "ml/min": ("mL/min", "flow"), "l/min": ("L/min", "flow"), "ml/h": ("mL/h", "flow"),
    "ml/hr": ("mL/h", "flow"), "lpm": ("L/min", "flow"),
    # pressure
    "mmhg": ("mmHg", "pressure"), "kpa": ("kPa", "pressure"), "pa": ("Pa", "pressure"),
    "psi": ("psi", "pressure"), "bar": ("bar", "pressure"),
    "cmh2o": ("cmH2O", "pressure"),
    # electrical
    "v": ("V", "voltage"), "mv": ("mV", "voltage"), "kv": ("kV", "voltage"),
    "ma": ("mA", "current"), "µa": ("µA", "current"), "ua": ("µA", "current"),
    "w": ("W", "power"), "mw": ("mW", "power"),
    "hz": ("Hz", "frequency"), "khz": ("kHz", "frequency"), "mhz": ("MHz", "frequency"),
    "ghz": ("GHz", "frequency"), "bps": ("bps", "rate"),
    # temperature
    "°c": ("°C", "temperature"), "ºc": ("°C", "temperature"), "degc": ("°C", "temperature"),
    "°f": ("°F", "temperature"), "ºf": ("°F", "temperature"),
    # mass and concentration
    "mg": ("mg", "mass"), "g": ("g", "mass"), "kg": ("kg", "mass"), "µg": ("µg", "mass"),
    "ug": ("µg", "mass"),
    "mg/ml": ("mg/mL", "concentration"), "mg/l": ("mg/L", "concentration"),
    "mmol/l": ("mmol/L", "concentration"), "meq/l": ("mEq/L", "concentration"),
    "%": ("%", "percentage"), "ppm": ("ppm", "concentration"),
    # time
    "ms": ("ms", "time"), "µs": ("µs", "time"), "us": ("µs", "time"),
    "s": ("s", "time"), "sec": ("s", "time"), "seconds": ("s", "time"),
    "min": ("min", "time"), "minutes": ("min", "time"),
    "h": ("h", "time"), "hr": ("h", "time"), "hours": ("h", "time"),
    # radiation and imaging
    "mgy": ("mGy", "dose"), "gy": ("Gy", "dose"), "kvp": ("kVp", "dose"),
    "mas": ("mAs", "dose"), "ct": ("ct", "other"),
}

#: Units whose names collide with ordinary English words are only accepted when a digit directly
#: precedes them, which the pattern already requires. ``g``, ``m``, ``l``, ``s``, ``in`` and ``ct``
#: are the ambiguous ones and are listed here so a change to the pattern cannot silently loosen them.
AMBIGUOUS = ("g", "m", "l", "s", "in", "ct", "v", "w", "h", "min")

NUMBER = r"\d{1,4}(?:[.,]\d{1,4})?"
_UNIT_ALTERNATION = "|".join(
    sorted((re.escape(unit) for unit in UNITS), key=len, reverse=True))
PATTERN = re.compile(
    rf"(?<![\w.])(?P<value>{NUMBER})\s*(?P<unit>{_UNIT_ALTERNATION})(?![\w])",
    re.IGNORECASE)

SENTENCE_SPLIT = re.compile(r"(?<=[.;:])\s+")
MAX_PARAMETERS = 400

ASSERTION = "manufacturer_statement_in_510k_summary"

#: Clause markers that mean the number is a clinical statistic, not a device parameter. Measured
#: need for this: without it, "approximately 30% to 50% are at high risk" and "5 L" from a
#: catalogue string were both returned as device specifications, and 30% of summaries produced
#: noise at that rate.
STATISTICS_MARKERS = (
    "patient", "patients", "subject", "subjects", "cohort", "study", "trial", "cases",
    "risk", "incidence", "prevalence", "sensitivity", "specificity", "accuracy",
    "confidence interval", "p =", "p<", "p <", "ci ", "odds ratio", "hazard ratio",
    "compared with", "versus", "vs.", "enrolled", "randomised", "randomized",
    "statistically", "mean", "median", "standard deviation", "follow-up", "adverse event",
)


def _is_clinical_statistics(clause: str) -> bool:
    lowered = f" {clause.lower()} "
    return any(marker in lowered for marker in STATISTICS_MARKERS)


#: Page furniture and federal-paperwork notices. Measured on K163337 and K223602: "Page 2 of 13"
#: and "DO NOT SEND YOUR COMPLETED FORM TO THE PRA STAFF EMAIL ADDRESS" both yielded parameters
#: ("22.9 cm", "79 h"). They are the two largest junk classes and both are exactly matchable.
BOILERPLATE_MARKERS = (
    "page ", " of 1", " of 2", " of 3", " of 4", " of 5", " of 6", " of 7", " of 8", " of 9",
    "do not send", "omb ", "paperwork reduction", "form approved", "pra ", "expiration date",
    "according to the paperwork", "public reporting burden", "table of contents",
    "confidential", "all rights reserved", "fda form", "cdrh", "rev. ", "version ",
)


def _is_boilerplate(clause: str) -> bool:
    lowered = f" {clause.lower()} "
    return any(marker in lowered for marker in BOILERPLATE_MARKERS)


@dataclass
class Parameter:
    value: str
    unit: str
    quantity: str
    sentence: str
    document: str = ""
    assertion: str = ASSERTION

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value, "unit": self.unit, "quantity": self.quantity,
                "sentence": self.sentence, "document": self.document,
                "assertion": self.assertion}


@dataclass
class DeviceSpecs:
    identifier: str
    parameters: list[Parameter] = field(default_factory=list)
    by_quantity: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    document_sections: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"identifier": self.identifier, "count": len(self.parameters),
                "by_quantity": self.by_quantity,
                "parameters": [p.to_dict() for p in self.parameters[:60]],
                "document_sections": self.document_sections,
                "assertion": ASSERTION}


def normalise_unit(raw: str) -> tuple[str, str] | None:
    return UNITS.get(raw.strip().lower().rstrip(".,"))


def _clause(text: str, start: int, end: int) -> str:
    """The sentence around a match, trimmed to something a reader can check."""
    left = 0
    for match in SENTENCE_SPLIT.finditer(text, 0, start):
        left = match.end()
    right_match = SENTENCE_SPLIT.search(text, end)
    right = right_match.end() if right_match else len(text)
    clause = " ".join(text[left:right].split())
    return clause[:400]


def extract_parameters(text: str, *, document: str = "") -> list[Parameter]:
    """Every number-with-unit in the text, each carrying the clause it came from."""
    if not text:
        return []
    found: list[Parameter] = []
    seen: set[tuple[str, str, str]] = set()
    for match in PATTERN.finditer(text):
        mapped = normalise_unit(match.group("unit"))
        if mapped is None:
            continue
        unit, quantity = mapped
        value = match.group("value").replace(",", ".")
        clause = _clause(text, match.start(), match.end())
        if _is_clinical_statistics(clause):
            # A percentage with a p-value beside it is a result, not a specification.
            continue
        if _is_boilerplate(clause):
            # Page furniture and OMB notices produce confident-looking numbers that are not specs.
            continue
        # "0.014 inch" and "0.014 in" are the same claim; dedupe on the normalised triple.
        key = (value, unit, clause[:80])
        if key in seen:
            continue
        seen.add(key)
        found.append(Parameter(value=value, unit=unit, quantity=quantity,
                               sentence=clause, document=document))
        if len(found) >= MAX_PARAMETERS:
            break
    return found


#: Sections most likely to state a parameter. ``device_description`` is the manufacturer's own
#: description; the others give the operating context. Reading only these keeps a number from an
#: unrelated boilerplate paragraph out of the result.
SPEC_SECTIONS = ("device_description", "indications", "principles_of_operation",
                 "specifications", "technical_description", "measurand")


def specs_from_sections(identifier: str, sections: Mapping[str, str]) -> DeviceSpecs:
    result = DeviceSpecs(identifier=identifier)
    for name, body in sections.items():
        if not body:
            continue
        if not any(key in name.lower() for key in SPEC_SECTIONS):
            continue
        result.document_sections.append(name)
        result.parameters.extend(extract_parameters(body, document=identifier))
    grouped: dict[str, list[dict[str, Any]]] = {}
    for parameter in result.parameters:
        grouped.setdefault(parameter.quantity, []).append(parameter.to_dict())
    result.by_quantity = {key: value[:20] for key, value in grouped.items()}
    return result


__all__ = [
    "ASSERTION",
    "DeviceSpecs",
    "Parameter",
    "SPEC_SECTIONS",
    "UNITS",
    "extract_parameters",
    "normalise_unit",
    "specs_from_sections",
]
