"""Admission of an observation into the user-facing intelligence feed.

Three layers, deliberately separate:

1. **Discovery** (in the adapters) is broad: a record is stored when a monitored source mentions a
   monitored company or topic. Nothing here can un-store it.
2. **Qualification** (this module) is strict: it asks whether the record is actually about a
   medical monitoring *technology* — a device, a measurement method, a monitoring system, a
   monitoring algorithm, or the engineering of one — rather than a clinical study that merely uses
   monitoring data or a paper that happens to contain a keyword.
3. **Publication** is the user view: only ``HIGH_RELEVANCE`` enters the default feed;
   ``NEEDS_REVIEW`` goes to a separate candidate area; ``LOW_RELEVANCE`` and ``IRRELEVANT`` stay in
   the ledger with their reason but are not shown as intelligence.

The judgement is rules over explicit features, versioned and stored; it is never written back onto
the observation itself, and a rejected record is not deleted.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

ADMISSION_VERSION = "radar-admission-2026.11.3"

HIGH_RELEVANCE = "HIGH_RELEVANCE"
NEEDS_REVIEW = "NEEDS_REVIEW"
LOW_RELEVANCE = "LOW_RELEVANCE"
IRRELEVANT = "IRRELEVANT"

TIER_ORDER = (HIGH_RELEVANCE, NEEDS_REVIEW, LOW_RELEVANCE, IRRELEVANT)

TIER_LABELS_ZH = {
    HIGH_RELEVANCE: "高相关",
    NEEDS_REVIEW: "有待核实",
    LOW_RELEVANCE: "低相关",
    IRRELEVANT: "无关",
}

#: Record types that are the company's own statements (or a regulator's). These are admitted as
#: source evidence: they are the subject, not an incidental keyword match.
AUTHORITATIVE_RECORD_TYPES = {"regulatory_record", "press_release", "product_document"}


def _rx(*patterns: str) -> re.Pattern[str]:
    return re.compile("|".join(f"(?:{p})" for p in patterns), re.IGNORECASE)


# --- vocabulary -----------------------------------------------------------------------------
# A device/measurement noun. "Monitoring" alone is a clinical activity, not a device, so it is not
# in this list; "patient monitor", "wearable sensor", "pulse oximeter" are.
_DEVICE = _rx(
    r"\bpatient monitors?\b", r"\bbedside monitors?\b", r"\bphysiologic(?:al)? monitors?\b",
    r"\bcardiac monitors?\b", r"\bmonitoring (?:system|device|platform|hardware|sensor)\b",
    r"\btelemetry\b", r"\bwearable (?:sensor|device|monitor|patch)\b",
    r"\b(?:pulse )?oximet(?:er|ry)s?\b", r"\bcapnogra(?:ph|phy)s?\b", r"\bspirometers?\b",
    r"\bventilators?\b", r"\b(?:infusion|syringe) pumps?\b", r"\belectrocardiographs?\b",
    r"\bholters?\b", r"\bdefibrillators?\b", r"\bblood pressure (?:monitor|cuff|device)s?\b",
    r"\bsphygmomanometers?\b", r"\btransducers?\b", r"\b(?:ecg|eeg|emg|eit) (?:device|sensor|patch|system)s?\b",
    r"\bmedical device\b", r"\bmonitoring device\b", r"\bsensor(s)?\b", r"\bprobe\b",
    r"\belectrodes?\b", r"\bimplantable monitor", r"\bremote monitoring\b",
    r"\bdevice[- ]based\b", r"\bpoint-of-care (?:device|testing)\b",
    r"\bsmart ?watch\b", r"\bsmartphone\b", r"\bwearable ecg\b", r"\becg monitoring\b", r"\bcardiac output monitor", r"\bhemodynamic monitor",
    r"\boxygenation monitor", r"\bbispectral index\b", r"\brespiratory monitor", r"\bapnea monitor",
    r"\bcontinuous glucose monitor", r"\bppg\b", r"\bphotoplethysmograph",
    r"\bmonitoring (?:technology|technologies|platform|algorithm|software)\b",
    r"\brespiratory support (?:device|system)s?\b", r"\boxygen titration\b",
    r"\balarm[- ]management (?:system|platform|solution)\b", r"\bcentral station\b",
    r"\bclinical decision support (?:system|platform)\b", r"\bpatient data management\b",
)
_ENGINEERING = _rx(
    r"\balgorithm", r"\bclassifier\b", r"\bdetector\b", r"\bsignal processing\b",
    r"\bwaveform", r"\bsampling rate\b", r"\bfeature extraction\b", r"\bfirmware\b",
    r"\bsoftware\b", r"\bcalibration\b", r"\bartifact (?:rejection|removal|detection)\b",
    r"\bnoise reduction\b", r"\bsignal[- ]to[- ]noise\b", r"\binteroperab", r"\bhl7\b", r"\bfhir\b",
    r"\bcybersecurity\b", r"\bdataset\b", r"\bbenchmark", r"\bphantom\b", r"\bbench (?:test|study)\b",
    r"\bin vitro\b", r"\bsimulation\b", r"\bdeep learning\b", r"\bmachine learning\b",
    r"\bneural network", r"\bcomputer vision\b", r"\bembedded\b", r"\bfalse alarm",
    r"\b(?:ai|artificial intelligence)[- ](?:model|algorithm|system|based|driven|ecg|enabled)",
    r"\b(?:signal|waveform)[- ](?:analysis|processing|classification|detection)\b",
    r"\b(?:medical )?iot\b",
    r"\barrhythmia classification\b",
    r"\b(?:arrhythmia|event|sepsis|deterioration) detection\b", r"\bsignal quality index\b",
    r"\bbiosignal", r"\bmachine[- ]learning\b", r"\bdeep[- ]learning\b",
)
_EVALUATION = _rx(
    r"\baccuracy\b", r"\bagreement\b", r"\bbland[- ]altman\b", r"\bvalidation\b",
    r"\bperformance (?:of|evaluation|assessment)\b", r"\bsensitivity and specificity\b",
    r"\bfalse (?:alarm|positive) rate\b", r"\bdetection (?:rate|performance|accuracy)\b",
    r"\bauc\b", r"\breference standard\b", r"\breproducib", r"\breliability\b",
    r"\bfeasibility\b", r"\bbench evaluation\b", r"\bhead-to-head\b", r"\bcompar",
    r"\bperformance\b", r"\b(?:improv|reduc|solv)\w*",
    r"\bdiscrepan", r"\bbias\b", r"\bclassification\b", r"\bwaveform quality\b",
    r"\bdetection\b", r"\bartifact", r"\bfalsely\b", r"\binaccura",
)
_DEVICE_STUDY = _rx(
    r"\bbench\b", r"\bphantom\b", r"\bin vitro\b", r"\baccuracy\b", r"\bagreement\b",
    r"\bvalidation\b", r"\bperformance evaluation\b", r"\bfalse alarm\b", r"\bsignal quality\b",
    r"\balgorithm performance\b", r"\bprospective (?:validation|evaluation)\b",
    r"\bcomparison (?:with|against) (?:the )?(?:reference|standard|device)\b",
    r"\bdevice (?:performance|accuracy|validation)\b",
)
_CLINICAL_ONLY = _rx(
    r"\brisk scor", r"\btimi\b", r"\bgrace score\b", r"\bapache\b", r"\bsofa score\b",
    r"\bmortality\b", r"\bmorbidity\b", r"\boutcomes?\b", r"\bcost[- ]effectiveness\b",
    r"\bprevalence\b", r"\bincidence\b", r"\bepidemiolog", r"\bcohort\b",
    r"\b(randomi[sz]ed|rct)\b", r"\btherapy\b", r"\btreatment\b", r"\bdrug\b", r"\bdose\b",
    r"\bsurgery\b", r"\bsurgical\b", r"\bstent\b", r"\bendoprosthes", r"\btransplant",
    r"\bquestionnaire\b", r"\bsurvey\b", r"\bquality improvement\b", r"\bnursing\b",
    r"\bpalliative\b", r"\bprognos", r"\bnomogram\b", r"\brisk stratification\b",
    r"\bprediction model\b", r"\bpredictive model\b", r"\brisk prediction\b",
)
_SETTING = _rx(
    r"\bicu\b", r"\bintensive care\b", r"\bcritical care\b", r"\bnicu\b", r"\bpicu\b",
    r"\boperating room\b", r"\bemergency department\b", r"\bperioperative\b", r"\bward\b",
    r"\bpostoperative\b", r"\banaesthesia\b", r"\banesthesia\b",
)
_NON_MEDICAL_STRONG = _rx(
    r"\bsmart grid\b", r"\bpower grid\b", r"\bwireless sensor network", r"\bpath loss\b",
    r"\bmilitary network", r"\bradioactive\b", r"\baerosol monitor", r"\bradiation monitor",
    r"\bindustrial\b", r"\bstructural health\b", r"\bmanufacturing\b", r"\bmining\b",
    r"\bvehicular network", r"\bcellular network\b", r"\bantenna array\b",
)
_CASE_VIGNETTE = _rx(
    r"^\s*[A-Z]\d{1,3}-\d{1,3}\b", r"\bcase report\b", r"\ba false alarm\b", r"\brare cause\b",
    r"\bunmasking\b", r"\bunmasks\b", r"\bin a patient with\b",
)

_NON_HUMAN = _rx(
    r"\b(?:horse|horses|equine|canine|feline|veterinary|bovine|poultry|swine|murine|rodent)\b",
    r"\banimal model\b", r"\bmice\b", r"\brats\b",
)
_NON_MEDICAL = _rx(
    r"\bsmart grid\b", r"\bpower grid\b", r"\belectrical infrastructure\b", r"\bindustrial\b",
    r"\bmanufacturing\b", r"\bstructural health\b", r"\btraffic monitoring\b",
    r"\bnetwork monitoring\b", r"\bserver monitoring\b", r"\bsoil\b", r"\bwater quality\b",
    r"\bair quality\b", r"\bclimate\b", r"\bagricultur", r"\boil (?:rig|pipeline)\b",
    r"\bisac\b", r"\bofdm\b", r"\b6g\b", r"\b5g\b", r"\btelecommunication",
    r"\bwireless communication\b", r"\bantenna\b",
    r"\bradioactive\b", r"\baerosol monitor", r"\bradiation monitor", r"\bnuclear\b",
    r"\bmining\b", r"\bmilitary\b",
)
_EDITORIAL = _rx(r"^\s*(?:editorial|commentary|comment|letter|erratum|correction|retraction)\b")

# MeSH terms are assigned by humans and are a stronger signal than title keywords.
_MESH_POSITIVE = _rx(
    r"equipment design", r"instrumentation", r"physiologic monitoring", r"signal processing",
    r"algorithms", r"equipment failure analysis", r"monitoring, physiologic",
    r"electrocardiography", r"diagnostic techniques, cardiovascular", r"computers",
)
_MESH_NEGATIVE = _rx(
    r"risk assessment", r"treatment outcome", r"retrospective studies",
    r"surveys and questionnaires", r"quality of life", r"cohort studies",
    r"prognosis", r"risk factors",
)
_ECONOMICS = _rx(
    r"\bcost[- ]effectiveness\b", r"\bcost[- ]benefit\b", r"\bbudget impact\b",
    r"\bhealth economic", r"\beconomic evaluation\b", r"\bcost[- ]utility\b",
)

_CROSSREF_ENGINEERING_SUBJECT = _rx(
    r"biomedical engineering", r"instrumentation", r"signal processing", r"medical informatics",
    r"health informatics", r"biotechnology", r"electrical engineering",
)


@dataclass(frozen=True)
class Admission:
    tier: str
    category: str
    score: float
    reasons: list[str] = field(default_factory=list)
    features: dict[str, Any] = field(default_factory=dict)

    def as_row(self) -> dict[str, Any]:
        return {
            "tier": self.tier,
            "category": self.category,
            "score": self.score,
            "reasons": json.dumps(self.reasons, ensure_ascii=False),
            "features": json.dumps(self.features, ensure_ascii=False),
        }


def _text_of(payload: Mapping[str, Any], title: str) -> str:
    parts = [title or ""]
    abstract = payload.get("abstract") or (payload.get("payload") or {}).get("abstract") or ""
    parts.append(str(abstract))
    parts.append(str(payload.get("journal") or payload.get("container_title") or ""))
    # Crossref ``subject`` values are bibliographic categories ("Industrial and Manufacturing
    # Engineering", "General Medicine"), not evidence about the study subject. They are kept out of
    # the exclusion text; a separate positive check reads them for an engineering category.
    terms = payload.get("mesh_terms") or []
    if isinstance(terms, list):
        parts.extend(str(item) for item in terms)
    return " \n ".join(parts)


def _count_hits(pattern: re.Pattern[str], text: str) -> int:
    return len(pattern.findall(text))


def classify_publication(*, title: str, payload: Mapping[str, Any]) -> Admission:
    """Qualification of a publication record."""
    text = _text_of(payload, title)
    title_text = title or ""
    abstract = str(payload.get("abstract") or (payload.get("payload") or {}).get("abstract") or "")
    features = {
        "has_abstract": len(abstract.strip()) > 120,
        "device_nouns": _count_hits(_DEVICE, text),
        "engineering": _count_hits(_ENGINEERING, text),
        "evaluation": _count_hits(_EVALUATION, text),
        "device_study": _count_hits(_DEVICE_STUDY, text),
        "clinical_only": _count_hits(_CLINICAL_ONLY, text),
        "setting": _count_hits(_SETTING, text),
        "non_human": _count_hits(_NON_HUMAN, text),
        "non_medical": _count_hits(_NON_MEDICAL, text),
        "mesh_positive": _count_hits(_MESH_POSITIVE, " ".join(
            str(t) for t in (payload.get("mesh_terms") or []))),
        "mesh_negative": _count_hits(_MESH_NEGATIVE, " ".join(
            str(t) for t in (payload.get("mesh_terms") or []))),
    }
    # A clinical prediction/risk-score paper is not monitoring technology, even when it uses
    # machine learning on monitoring data. The distinguishing question is whether the *object*
    # of the paper is a device/algorithm and its performance, which is a title-level question:
    # abstracts of clinical papers routinely mention the monitor they took data from.
    # Titles arrive with JATS markup and typographic dashes ("cost‐effectiveness" uses U+2010).
    # Matching must see the words, not the publisher's typography.
    title_clean = re.sub(r"<[^>]+>", " ", title_text)
    title_clean = re.sub(r"[\u2010-\u2015\u2212\u00a0]", lambda m: "-" if m.group(0) != "\u00a0" else " ", title_clean)
    title_clean = re.sub(r"\s+", " ", title_clean).strip()
    title_lower = title_clean.lower()
    features["title_device"] = bool(_DEVICE.search(title_text))
    features["title_engineering"] = bool(_ENGINEERING.search(title_text))
    features["title_evaluation"] = bool(
        _EVALUATION.search(title_text) or _DEVICE_STUDY.search(title_text)
        or re.search(r"\bevaluat|\bvalidat|\bbench\b|\bphantom\b|\bdevelopment\b|\bdesign\b|"
                     r"\barchitecture\b|\bfeasibility\b", title_lower)
    )
    features["clinical_prediction_title"] = bool(
        re.search(r"predict|prediction|prognos|risk (?:score|stratification|factor)|mortality|"
                  r"outcome|diagnostic accuracy", title_lower)
        and re.search(r"model|machine learning|deep learning|algorithm|nomogram|score|predictor", title_lower)
    ) and not (
        re.search(r"\bdevice|\bmonitor|\bsensor|\bwearable|\boximeter|\bventilator|\bholter|"
                  r"\bprobe|\btransducer|\bsmart ?watch|\bsmartphone|\biot\b", title_lower)
        and features["title_evaluation"]
    )
    features["health_it_title"] = bool(re.search(r"\b(?:fhir|hl7|interoperab)", title_lower))
    features["title_review"] = bool(re.search(
        r"\b(?:systematic|narrative|scoping|literature) review\b", title_lower))
    features["title_signal"] = bool(re.search(
        r"\b(?:ecg|eeg|emg|eit|arrhythmia|waveform|vital[- ]signs?|physiolog\w*|oximet\w*|spo2|"
        r"blood pressure|capnograph\w*|photoplethysmograph\w*|ppg)\b", title_lower))
    reasons: list[str] = []

    # Hard exclusions: a veterinary or industrial record is not ICU monitoring intelligence.
    if features["non_human"] and not features["mesh_positive"]:
        return Admission(IRRELEVANT, "non_human_subject", -10.0,
                         ["subjects are animals, not patients"], features)
    if _NON_MEDICAL_STRONG.search(text):
        return Admission(IRRELEVANT, "non_medical_domain", -10.0,
                         ["the monitored system is not a patient (grid/industrial/military/radiation)"],
                         features)
    if features["non_medical"] and not features["device_nouns"]:
        return Admission(IRRELEVANT, "non_medical_domain", -10.0,
                         ["the monitored system is not a patient"], features)
    if _CASE_VIGNETTE.search(title_text):
        return Admission(LOW_RELEVANCE, "case_report", -2.0,
                         ["single-case vignette, not monitoring-technology research"], features)
    if _EDITORIAL.search(title_text):
        return Admission(LOW_RELEVANCE, "editorial_or_letter", -6.0,
                         ["editorial/letter, not a study"], features)
    if features["clinical_prediction_title"]:
        return Admission(LOW_RELEVANCE, "clinical_prediction_model", -1.0,
                         ["clinical prediction/risk study, not a monitoring technology"], features)
    if _ECONOMICS.search(title_lower):
        return Admission(LOW_RELEVANCE, "health_economics", -1.0,
                         ["health-economic analysis, not monitoring technology"], features)
    if features["health_it_title"] and not features["title_device"]:
        return Admission(NEEDS_REVIEW, "health_it_interoperability", 2.0,
                         ["health-IT interoperability; no monitoring device evaluated"], features)

    score = 0.0
    if features["device_nouns"]:
        score += 3.0
        reasons.append("names a monitoring device or sensor")
    if features["engineering"]:
        score += 2.0
        reasons.append("engineering/algorithm content")
    if features["evaluation"]:
        score += 2.0
        reasons.append("evaluates performance or accuracy")
    if features["device_study"]:
        score += 2.0
        reasons.append("device/algorithm evaluation design")
    if features["mesh_positive"]:
        score += 2.0
        reasons.append("MeSH marks instrumentation/engineering")
    if features["setting"]:
        score += 1.0
        reasons.append("set in acute/critical care")
    device_evaluation_title = features["title_device"] and features["title_evaluation"]
    if features["clinical_only"] and not device_evaluation_title:
        score -= 2.0
        reasons.append("clinical outcome/risk framing")
    if features["mesh_negative"] and not features["device_study"]:
        score -= 1.0
        reasons.append("MeSH marks clinical risk/outcome work")
    if features["title_review"] and features["title_signal"]:
        score += 3.0
        reasons.append("structured review of monitoring technology")
    if not features["has_abstract"]:
        score -= 0.5
        reasons.append("no abstract: judged from the title only")
    if _CROSSREF_ENGINEERING_SUBJECT.search(" ".join(str(s) for s in (payload.get("subject") or []))):
        score += 1.0
        reasons.append("indexed under an engineering subject")

    # High relevance requires the title itself to be about a monitoring technology *and* to
    # evaluate/validate/design it. A clinical paper that merely mentions a monitor in its abstract
    # cannot reach this tier.
    title_technology_evaluation = (features["title_evaluation"] or (features["title_review"] and features["title_signal"])) and (
        features["title_device"]
        or (features["title_engineering"]
            and (features["device_nouns"] or features["setting"] or features["mesh_positive"]
                 or features["device_study"] or features["title_signal"]))
        or (features["title_review"] and features["title_signal"])
    )
    if title_technology_evaluation and score >= 4.5:
        tier = HIGH_RELEVANCE
        category = "monitoring_technology_evaluation"
    elif features["device_nouns"] and features["engineering"] and score >= 4.0 and not features["clinical_only"]:
        tier = NEEDS_REVIEW
        category = "device_or_algorithm_needs_confirmation"
        reasons.append("device + engineering signals, no explicit performance evaluation")
    elif (features["device_nouns"] or features["engineering"]) and score >= 3.0:
        tier = NEEDS_REVIEW
        category = "plausible_monitoring_technology"
    elif features["clinical_only"] and not features["device_nouns"]:
        tier = LOW_RELEVANCE
        category = "clinical_study_without_device_focus"
        reasons.append("clinical question, no monitoring technology under study")
    elif not (features["device_nouns"] or features["engineering"]):
        tier = IRRELEVANT if score <= 0 else LOW_RELEVANCE
        category = "no_monitoring_technology"
        reasons.append("neither a monitoring device nor monitoring engineering appears")
    else:
        tier = LOW_RELEVANCE
        category = "weak_monitoring_signal"
    return Admission(tier, category, round(score, 2), reasons, features)


def classify_observation(record: Mapping[str, Any], *, mapped_topics: Sequence[str] | None = None,
                         mapped_products: Sequence[str] | None = None) -> Admission:
    """Qualification for one observation row (``record_type`` + ``title`` + payload)."""
    record_type = str(record.get("record_type") or "")
    payload_raw = record.get("payload")
    if isinstance(payload_raw, str):
        try:
            payload = json.loads(payload_raw)
        except json.JSONDecodeError:
            payload = {}
    else:
        payload = dict(payload_raw or {})
    title = str(record.get("title") or "")
    if record_type in AUTHORITATIVE_RECORD_TYPES:
        # The company's own statement or the regulator's record *is* the subject. Admitted, with
        # its evidence class kept distinct from a capability claim — but only when the mapping
        # actually placed it in a monitored topic or product. A board-appointment press release is
        # still a primary source and still not monitoring intelligence.
        if not mapped_topics and not mapped_products:
            return Admission(LOW_RELEVANCE, "primary_record_unmapped", 0.0,
                             ["primary source, but it mentions no monitored product or topic"], {})
        category = {
            "regulatory_record": "regulatory_record",
            "press_release": "vendor_statement",
            "product_document": "vendor_statement",
        }[record_type]
        return Admission(HIGH_RELEVANCE, category, 10.0,
                         ["a primary record from a monitored source"], {"authoritative": True})
    if record_type == "publication":
        return classify_publication(title=title, payload=payload)
    return Admission(NEEDS_REVIEW, "unclassified_record_type", 0.0,
                     [f"record type {record_type!r} has no qualification rule"], {})


def tier_for_label(label: str) -> str:
    """Map a human label to the engine tier, for the evaluation set."""
    return label


def summarize(admissions: Iterable[Admission]) -> dict[str, int]:
    counts = {tier: 0 for tier in TIER_ORDER}
    for admission in admissions:
        counts[admission.tier] = counts.get(admission.tier, 0) + 1
    return counts


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


__all__ = [
    "ADMISSION_VERSION",
    "Admission",
    "HIGH_RELEVANCE",
    "NEEDS_REVIEW",
    "LOW_RELEVANCE",
    "IRRELEVANT",
    "TIER_ORDER",
    "TIER_LABELS_ZH",
    "AUTHORITATIVE_RECORD_TYPES",
    "classify_observation",
    "classify_publication",
    "summarize",
    "now_iso",
]
