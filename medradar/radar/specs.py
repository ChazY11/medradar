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
    "µm": ("µm", "length"), "μm": ("µm", "length"), "um": ("µm", "length"),
    "micron": ("µm", "length"), "microns": ("µm", "length"), "nm": ("nm", "length"),
    # rotational speed: centrifuges, surgical motors, drill consoles
    "rpm": ("rpm", "speed"), "rpm.": ("rpm", "speed"),
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

#: Six integer digits: "10000 mL/min" and "12000 rpm" are real specifications, and the four-digit
#: ceiling that used to live here silently dropped every five-digit value - a recall hole that read
#: as high precision. The plausibility range below is what now keeps the impossible ones out, so the
#: pattern may be generous.
NUMBER = r"\d{1,6}(?:[.,]\d{1,4})?"
_UNIT_ALTERNATION = "|".join(
    sorted((re.escape(unit) for unit in UNITS), key=len, reverse=True))
PATTERN = re.compile(
    rf"(?<![\w.])(?P<value>{NUMBER})\s*(?P<unit>{_UNIT_ALTERNATION})(?![\w])",
    re.IGNORECASE)

SENTENCE_SPLIT = re.compile(r"(?<=[.;:])\s+")
MAX_PARAMETERS = 400

ASSERTION = "manufacturer_statement_in_510k_summary"

#: What a number in each unit can physically be on a medical device.
#:
#: Measured on the harvested corpus: a raw number-with-unit scan keeps about 40% of what it finds
#: after page furniture is removed, and a further share is arithmetically impossible - a steam
#: steriliser "250 °F" is a real specification, "12500 °F" is an OCR artefact or a model number
#: that happened to sit next to a degree sign. Ranges are deliberately generous at both ends: the
#: job is to drop the impossible, not to second-guess a manufacturer.
PLAUSIBLE: dict[str, tuple[float, float]] = {
    # length
    "mm": (0.001, 5000.0), "cm": (0.001, 500.0), "m": (0.0001, 50.0),
    "in": (0.0001, 500.0), "ft": (0.001, 100.0),
    "µm": (0.0001, 5000.0), "nm": (0.0001, 100000.0),
    # rotational speed
    "rpm": (0.1, 200000.0),
    # gauges: French and Birmingham wire gauge both live in the low tens
    "Fr": (0.5, 40.0), "ga": (0.5, 40.0),
    # volume and flow
    "mL": (0.0001, 20000.0), "L": (0.00001, 500.0), "µL": (0.0001, 100000.0),
    "mL/min": (0.0001, 20000.0), "L/min": (0.00001, 500.0), "mL/h": (0.0001, 20000.0),
    # pressure
    "mmHg": (0.01, 2000.0), "kPa": (0.001, 300.0), "Pa": (0.01, 300000.0),
    "psi": (0.01, 2000.0), "bar": (0.0001, 200.0), "cmH2O": (0.01, 1000.0),
    # electrical
    "V": (0.001, 100000.0), "mV": (0.0001, 100000.0), "kV": (0.001, 500.0),
    "mA": (0.0001, 20000.0), "µA": (0.0001, 1000000.0),
    "W": (0.0001, 20000.0), "mW": (0.0001, 100000.0),
    "Hz": (0.01, 1000000.0), "kHz": (0.001, 1000.0), "MHz": (0.0001, 200.0),
    "GHz": (0.00001, 20.0), "bps": (1.0, 1000000000.0),
    # temperature, negative allowed
    "°C": (-100.0, 2000.0), "°F": (-148.0, 3600.0),
    # mass and concentration
    "mg": (0.0001, 100000.0), "g": (0.0001, 10000.0), "kg": (0.0001, 1000.0),
    "µg": (0.0001, 10000000.0),
    "mg/mL": (0.00001, 2000.0), "mg/L": (0.00001, 100000.0),
    "mmol/L": (0.00001, 5000.0), "mEq/L": (0.00001, 1000.0),
    "%": (0.0, 100.0), "ppm": (0.0, 1000000.0),
    # time
    "ms": (0.0001, 10000000.0), "µs": (0.0001, 1000000000.0),
    "s": (0.00001, 1000000.0), "min": (0.00001, 100000.0), "h": (0.00001, 10000.0),
    # radiation and imaging
    "mGy": (0.00001, 500.0), "Gy": (0.000001, 100.0),
    "kVp": (10.0, 300.0), "mAs": (0.01, 5000.0),
}

#: Units that carry no numeric magnitude, so no range can be checked.
NON_NUMERIC_UNITS = frozenset({"ct"})

_THOUSANDS = re.compile(r"^\d{1,3}(?:,\d{3})+(?:\.\d+)?$")
_DECIMAL_COMMA = re.compile(r"^\d+,\d+$")


def parse_number(raw: str) -> float | None:
    """Read a printed number without guessing its locale wrongly.

    ``1,000`` in an English 510(k) summary is one thousand; ``1,5`` in a translated one is one and
    a half. A blanket ``replace(",", ".")`` turns the first into 1.0 and silently understates a
    specification by three orders of magnitude, which is worse than dropping it.
    """
    text = str(raw or "").strip().replace(" ", "")
    if not text:
        return None
    if _THOUSANDS.match(text):
        text = text.replace(",", "")
    elif _DECIMAL_COMMA.match(text):
        text = text.replace(",", ".")
    else:
        text = text.replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None


def implausibility(value: str, unit: str) -> str | None:
    """Why a value cannot be a specification in this unit, or ``None`` if it can."""
    if unit in NON_NUMERIC_UNITS:
        return None
    bounds = PLAUSIBLE.get(unit)
    if bounds is None:
        return None
    number = parse_number(value)
    if number is None:
        return "not a number"
    low, high = bounds
    if number < low or number > high:
        return f"{value} {unit} is outside the physically possible {low:g}-{high:g} {unit}"
    return None

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


#: Quantities whose unit alone proves nothing. A percentage is a specification when the clause says
#: what it measures ("accuracy of ± 2 %", "relative humidity 30 %"), and is page noise otherwise:
#: measured on 1,802 real summaries, a bare "2 %" / "42 %" / "0 %" run from a form table survived
#: both the statistics and the boilerplate filter. Other quantities (mm, psi, mL/min) carry their own
#: evidence in the unit and need no cue.
AMBIGUOUS_QUANTITIES = frozenset({"percentage"})

#: Words that turn an ambiguous number into a claim about the device.
SPEC_CUES = (
    "accuracy", "tolerance", "±", "+/-", "up to", "maximum", "minimum", " max", " min",
    "range", "capacity", "diameter", "length", "width", "height", "weight", "pressure",
    "temperature", "flow", "rate", "concentration", "humidity", "precision", "resolution",
    "output", "input", "dose", "deliver", "infus", "volume", "speed", "torque", "voltage",
    "current", "power", "frequency", "battery", "cycle", "duration", "exposure", "steriliz",
    "filled", "oxygen", "saturation", "slope", "gradient", "efficiency", "grade", "purity",
)


def _has_spec_cue(clause: str) -> bool:
    lowered = clause.lower()
    return any(cue in lowered for cue in SPEC_CUES)


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
    rejected: int = 0
    rejected_examples: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"identifier": self.identifier, "count": len(self.parameters),
                "rejected_implausible": self.rejected,
                "rejected_examples": self.rejected_examples[:5],
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


def extract_parameters(text: str, *, document: str = "",
                       diagnostics: dict[str, Any] | None = None) -> list[Parameter]:
    """Every *plausible* number-with-unit in the text, each carrying the clause it came from.

    ``diagnostics`` collects what was dropped and why, so a caller can report "found 61, kept 40,
    rejected 21 as impossible" instead of quietly returning a shorter list. A silent filter is
    indistinguishable from a source that had less to say.
    """
    if not text:
        return []
    found: list[Parameter] = []
    seen: set[tuple[str, str, str]] = set()
    rejected = 0
    examples: list[dict[str, str]] = []
    for match in PATTERN.finditer(text):
        mapped = normalise_unit(match.group("unit"))
        if mapped is None:
            continue
        unit, quantity = mapped
        value = match.group("value")
        clause = _clause(text, match.start(), match.end())
        # "± 2 %" is a tolerance whether or not the same clause also says "accuracy". Without this
        # precedence a tolerance line is thrown away by the statistics filter, which lists
        # "accuracy" because diagnostic-accuracy studies quote it as an outcome.
        strong_spec = any(mark in clause for mark in ("±", "+/-", "tolerance"))
        if not strong_spec and _is_clinical_statistics(clause):
            # A percentage with a p-value beside it is a result, not a specification.
            continue
        if _is_boilerplate(clause):
            # Page furniture and OMB notices produce confident-looking numbers that are not specs.
            continue
        why = implausibility(value, unit)
        if why:
            rejected += 1
            if len(examples) < 8:
                examples.append({"value": value, "unit": unit, "why": why,
                                 "sentence": clause[:200]})
            continue
        if quantity in AMBIGUOUS_QUANTITIES and not _has_spec_cue(clause):
            # A bare percentage with nothing saying what it measures is a form field, not a spec.
            rejected += 1
            if len(examples) < 8:
                examples.append({"value": value, "unit": unit,
                                 "why": "percentage with no specification cue in the clause",
                                 "sentence": clause[:200]})
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
    if diagnostics is not None:
        diagnostics["rejected"] = rejected
        diagnostics["rejected_examples"] = examples
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
        diagnostics: dict[str, Any] = {}
        result.parameters.extend(
            extract_parameters(body, document=identifier, diagnostics=diagnostics))
        result.rejected += int(diagnostics.get("rejected") or 0)
        result.rejected_examples.extend(diagnostics.get("rejected_examples") or [])
    grouped: dict[str, list[dict[str, Any]]] = {}
    for parameter in result.parameters:
        grouped.setdefault(parameter.quantity, []).append(parameter.to_dict())
    result.by_quantity = {key: value[:20] for key, value in grouped.items()}
    result.rejected_examples = result.rejected_examples[:8]
    return result


__all__ = [
    "ASSERTION",
    "DeviceSpecs",
    "NON_NUMERIC_UNITS",
    "PLAUSIBLE",
    "Parameter",
    "SPEC_SECTIONS",
    "UNITS",
    "extract_parameters",
    "implausibility",
    "normalise_unit",
    "parse_number",
    "specs_from_sections",
]
