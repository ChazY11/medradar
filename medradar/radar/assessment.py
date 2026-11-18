"""Multi-dimensional monitoring-technology relevance assessment (REFOUNDATION-004).

Why this module exists
----------------------
QUALITY-001 used one label, HIGH_RELEVANCE, to carry eight different judgements at once:
source authenticity, medical domain, monitoring relevance, transfer value, entity linkage,
freshness, importance and confidence. A single tier cannot mean all of those things, and the
consequences were concrete and measurable:

* an official Philips imaging launch was HIGH because the source was authentic (source
  authenticity was substituted for subject judgement);
* an ECG arrhythmia-classification paper in an electrical-engineering journal was IRRELEVANT
  because the journal title contained the word "Telecommunications" (venue text was treated as
  subject evidence);
* an oil-leak detector, a radar-odometry detector and an IoT interference-suppression paper were
  HIGH or NEEDS_REVIEW because "false alarm" and "detector" are engineering words (keyword match
  was treated as topic judgement);
* 7,166 of 8,593 observations (83%) were HIGH, so the label carried almost no information.

This module replaces the single tier with explicit dimensions and one decision policy. The
dimensions are independent on purpose; a caller can show "official source, not monitoring
technology" instead of a misleading badge.

Dimensions
----------
source_authenticity  PRIMARY_REGULATORY | OFFICIAL_VENDOR | SCHOLARLY | SECONDARY
medical_domain       MEDICAL | NON_MEDICAL | UNCERTAIN
monitoring_relevance DIRECT | TRANSFER | CLINICAL | MEDICAL_UNRELATED | NON_MEDICAL
entity_link          NONE | AFFILIATION | VENDOR | APPLICANT
freshness            FRESH | RECENT | STALE | UNKNOWN (from the source-stated date and its precision)
importance           CRITICAL | HIGH | MEDIUM | LOW, graded by grade_importance() from the record
                     type, the safety content of an official reason for recall, the monitoring
                     relevance, the freshness and whether the record evaluates the measurement
                     itself. Every grade carries its reasons in dimensions["importance_reasons"];
                     no quota and no fixed ratio is imposed.
confidence           0..1 in the monitoring_relevance judgement
decision             FEED | REVIEW | EXCLUDED

The judgement separates the *role* of the text it reads:

* subject text (title, abstract, official summary) is the only text that can establish what the
  record is about;
* venue text (journal, container title) may support an engineering-venue signal but can never
  make a record non-medical or irrelevant - that was the ECG-in-an-engineering-journal bug;
* index text (MeSH, Crossref subject categories) is a weak positive signal only;
* entity text (applicant, publisher) establishes entity linkage, never relevance. An official
  company is not a monitoring-technology claim.

Nothing here deletes or rewrites an observation. A rejected record keeps its reason.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Sequence

from .recall import is_recall_payload, screen_recall
from .records import effective_precision

# --------------------------------------------------------------------------- version
#: Bumped whenever the vocabulary, thresholds or policy change. Stored on every decision.
ASSESSMENT_VERSION = "radar-assessment-2026.11.21"
ADMISSION_VERSION = ASSESSMENT_VERSION  # backward-compatible name used by the ledger and API
RULES_VERSION = "assessment-rules-2026.11.21"

# --------------------------------------------------------------------------- tiers
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

# --------------------------------------------------------------------------- dimensions
DECISION_FEED = "FEED"
DECISION_REVIEW = "REVIEW"
DECISION_EXCLUDED = "EXCLUDED"
DECISIONS = (DECISION_FEED, DECISION_REVIEW, DECISION_EXCLUDED)

DIRECT = "DIRECT"
TRANSFER = "TRANSFER"
CLINICAL = "CLINICAL"
MEDICAL_UNRELATED = "MEDICAL_UNRELATED"
NON_MEDICAL = "NON_MEDICAL"
MONITORING_RELEVANCE_CLASSES = (DIRECT, TRANSFER, CLINICAL, MEDICAL_UNRELATED, NON_MEDICAL)

MEDICAL = "MEDICAL"
UNCERTAIN_DOMAIN = "UNCERTAIN"
MEDICAL_DOMAINS = (MEDICAL, NON_MEDICAL, UNCERTAIN_DOMAIN)

PRIMARY_REGULATORY = "PRIMARY_REGULATORY"
OFFICIAL_VENDOR = "OFFICIAL_VENDOR"
SCHOLARLY = "SCHOLARLY"
SECONDARY = "SECONDARY"
SOURCE_AUTHENTICITY = (PRIMARY_REGULATORY, OFFICIAL_VENDOR, SCHOLARLY, SECONDARY)

ENTITY_NONE = "NONE"
ENTITY_AFFILIATION = "AFFILIATION"
ENTITY_VENDOR = "VENDOR"
ENTITY_APPLICANT = "APPLICANT"
ENTITY_LINKS = (ENTITY_NONE, ENTITY_AFFILIATION, ENTITY_VENDOR, ENTITY_APPLICANT)

FRESH = "FRESH"
RECENT = "RECENT"
STALE = "STALE"
FRESHNESS_UNKNOWN = "UNKNOWN"
FRESHNESS_VALUES = (FRESH, RECENT, STALE, FRESHNESS_UNKNOWN)

IMPORTANCE_CRITICAL = "CRITICAL"
IMPORTANCE_HIGH = "HIGH"
IMPORTANCE_MEDIUM = "MEDIUM"
IMPORTANCE_LOW = "LOW"
#: Ordered most important first; the brief and the API render in this order.
IMPORTANCE_LEVELS = (IMPORTANCE_CRITICAL, IMPORTANCE_HIGH, IMPORTANCE_MEDIUM, IMPORTANCE_LOW)
IMPORTANCE_VALUES = IMPORTANCE_LEVELS

#: Record types whose text is the issuer's own statement about the subject.
PRIMARY_RECORD_TYPES = {"regulatory_record", "press_release", "product_document"}
#: Backward-compatible alias used by the earlier module and by callers.
AUTHORITATIVE_RECORD_TYPES = PRIMARY_RECORD_TYPES

#: Monitoring topic families that describe a device or its measurement chain. A topic in one of
#: these families is device evidence; a topic in decision_support or integration is not, on its
#: own, a device.
DEVICE_FAMILIES = frozenset({
    "electrocardiography", "oxygenation", "haemodynamics", "ventilation", "alarms", "platform",
})
DEVICE_TOPICS = frozenset({"data_interoperability"})


def _rx(*patterns: str) -> re.Pattern[str]:
    return re.compile("|".join("(?:%s)" % p for p in patterns), re.IGNORECASE)


# --------------------------------------------------------------------------- vocabulary
#: A monitoring device or monitoring platform. These are strong: they name the class of device.
DEVICE_STRONG = _rx(
    r"\bpatient monitors?\b", r"\bbedside monitors?\b", r"\bphysiologic(?:al)? monitors?\b",
    r"\bcardiac monitors?\b", r"\bmonitor(?:ing)? (?:system|device|platform|hardware)\b",
    r"\b(?:central|telemetry) (?:station|system)\b", r"\btelemetry\b",
    r"\b(?:pulse )?oximet(?:er|ry)s?\b", r"\bcapnogra(?:ph|phy|phic)\b",
    r"\belectrocardiogra(?:m|ph|phic|phy)s?\b", r"\b(?:ecg|ekg|eeg|emg|eit) (?:device|sensor|patch|system|monitor|electrode|recorder)s?\b",
    r"\bholters?\b", r"\bventilators?\b", r"\bblood pressure (?:monitor|cuff|device|measurement)s?\b",
    r"\bsphygmomanometers?\b", r"\b(?:infusion|syringe) pumps?\b", r"\bdefibrillators?\b",
    r"\bcontinuous glucose monitors?\b", r"\bwearable (?:sensor|device|monitor|patch|ecg|oximeter)s?\b",
    r"\bphotoplethysmogra(?:ph|phy|phic)\b", r"\bppg\b",
    r"\bnear[- ]infrared spectroscopy\b", r"\bnirs\b", r"\bcerebral oximet(?:er|ry)s?\b",
    r"\binvasive blood pressure\b", r"\barterial (?:line|pressure monitor)\b",
    r"\bha?emodynamic monitor\b", r"\bcardiac output monitor\b", r"\brespiratory monitor\b",
    r"\bapnea monitor\b", r"\balarm (?:algorithm|system|management system|management platform)\b",
    r"\bcentral station\b", r"\bclinical (?:sensor|monitoring)\b",
    r"\bmonitoring (?:algorithm|platform|software|technology)\b",
    r"\bairway pressure monitor\b", r"\btemperature monitor\b",
    r"\bsensor system\b", r"\binertial measurement\b", r"\baccelerometer", r"\bgyroscope",
    r"\bsmartphone telemetry\b", r"\bsmartphone technology\b",
    r"\bsmart alarm\b", r"\balarm algorithm\b", r"\balarm management (?:system|platform|solution)\b",
    r"\bwearable (?:system|technology|sensing)\b",
)
#: A physiological measurement that monitoring technology performs or studies.
MEASUREMENT_STRONG = _rx(
    r"\boxygen saturation\b", r"\bs(?:a|p|t|v|c)o2\b", r"\bspo2\b", r"\boximetry\b",
    r"\bcerebral (?:oxygen|oxygenation|saturation)\b", r"\btissue (?:oxygen|oxygenation|saturation)\b",
    r"\bend[- ]tidal (?:co2|carbon dioxide)\b", r"\bcapnometry\b",
    r"\belectrocardiogra(?:m|phy|phic)s?\b", r"\belectroencephalogra(?:m|phy|phic)s?\b",
    r"\bcontinuous (?:eeg|electroencephalogram)\b", r"\barrhythmia (?:detection|classification|monitoring)\b",
    r"\b(?:ecg|eeg|emg|eit) (?:signal|waveform|classification|monitoring|analysis|recording)s?\b",
    r"\bsingle-lead ecg\b", r"\bmulti-lead ecg\b", r"\bcardiorespiratory monitoring\b",
    r"\bphysiological monitoring\b", r"\bvital[- ]signs? monitoring\b", r"\bremote (?:patient )?monitoring\b",
    r"\bcardiac (?:rhythm|telemetry) monitoring\b", r"\bintracranial pressure monitoring\b",
    r"\bfetal (?:heart rate|monitoring)\b", r"\bglucose monitoring\b", r"\bperfusion index\b",
    r"\bheart rate variability\b", r"\bcontinuous (?:temperature|blood pressure|cardiac) monitoring\b",
    r"\bhemodynamic (?:parameter|monitoring|measurement)s?\b",
    r"\bha?emodynamic (?:parameter|monitoring|measurement)s?\b",
    r"\bnon[- ]invasive (?:blood pressure|monitoring)\b", r"\bnibp\b",
    r"\binvasive (?:bp|blood pressure)\b",
    r"\bcardiorespiratory\b",
    r"\bmonitoring data\b", r"\bwaveform (?:analysis|quality|monitoring)\b",
    r"\bphysiological (?:signal|biomarker)[- ]monitoring\b", r"\bbiomarker monitoring\b",
    r"\boxygen titration\b", r"\bautomated oxygen\b",
)
#: Engineering of a measurement/device (the object can be the algorithm itself).
ENGINEERING = _rx(
    r"\balgorithm", r"\bclassifier\b", r"\bdetector\b", r"\bsignal processing\b",
    r"\bsignal quality\b", r"\bfeature extraction\b", r"\bfirmware\b",
    r"\bartifact (?:rejection|removal|detection)\b", r"\bnoise reduction\b",
    r"\bsignal[- ]to[- ]noise\b", r"\bbench (?:test|study|evaluation)\b", r"\bphantom\b",
    r"\bin vitro\b", r"\bdeep learning\b", r"\bmachine[- ]learning\b",
    r"\bneural network", r"\bconvolutional\b", r"\btransformer model\b",
    r"\bfalse (?:alarm|positive) (?:rate|reduction|suppression|detection)\b", r"\bfalse alarms?\b",
    r"\b(?:ai|artificial intelligence)[- ](?:model|algorithm|system|based|driven|ecg|enabled)",
    r"\bedge (?:inference|computing|intelligence)\b", r"\bembedded\b", r"\bcalibration\b",
    r"\binteroperab", r"\bhl7\b", r"\bfhir\b", r"\bsensor fusion\b",
)
#: A study that evaluates the device or algorithm rather than a clinical question.
EVALUATION = _rx(
    r"\baccuracy\b", r"\bagreement\b", r"\bbland[- ]altman\b", r"\bvalidation\b",
    r"\bvalidat(?:e|ing|ed)\b", r"\bperformance (?:of|evaluation|assessment|comparison)?\b",
    r"\bsensitivity and specificity\b", r"\bfalse (?:alarm|positive) rate\b",
    r"\bdetection (?:rate|performance|accuracy)\b", r"\bauc\b", r"\breference standard\b",
    r"\breproducib", r"\bfeasibility\b", r"\bbench evaluation\b", r"\bhead-to-head\b",
    r"\bcompar(?:ison|ing|ed|e)\b", r"\bdiscrepan", r"\bbias\b", r"\bdetection\b",
    r"\bclassification\b", r"\bconcordance\b", r"\bevaluat", r"\bassessment of\b",
    r"\bcharacteri[sz]ation\b", r"\btest[- ]retest\b",
)
#: Clinical care/outcome framing. Its presence with a measurement term usually means the record
#: is about a clinical question that consumed monitoring data.
CLINICAL_APPLICATION = _rx(
    r"\bmortality\b", r"\bmorbidity\b", r"\boutcomes?\b", r"\bcost[- ]effectiveness\b",
    r"\bcost[- ]benefit\b", r"\bhealth economic", r"\bprevalence\b", r"\bincidence\b",
    r"\bepidemiolog", r"\bcohort\b", r"\brandomi[sz]ed\b", r"\brct\b",
    r"\btherapy\b", r"\btreatment\b", r"\bdrug\b", r"\bdose\b", r"\bdosing\b",
    r"\bsurgery\b", r"\bsurgical\b", r"\bperioperative\b", r"\bpostoperative\b",
    r"\banaesthesia\b", r"\banesthesia\b", r"\bstent\b", r"\btransplant",
    r"\bquestionnaire\b", r"\bsurvey\b", r"\bquality improvement\b", r"\bnursing\b",
    r"\bpalliative\b", r"\bprognos", r"\bnomogram\b", r"\brisk (?:score|stratification|factor|prediction)\b",
    r"\bprediction model\b", r"\bpredictive model\b", r"\brisk model\b",
    r"\bpredict(?:s|ed|ing|ion|ive)?\b", r"\bforecast", r"\badverse events?\b",
    r"\breadmission\b", r"\blength of stay\b", r"\bweaning\b", r"\bextubation\b",
    r"\borgan failure\b", r"\bsepsis\b", r"\bdelirium\b", r"\blinezolid\b",
    r"\bbiomarker", r"\bbnp\b", r"\bnt-probnp\b", r"\bheart failure (?:assessment|risk|outcome)\b",
    r"\bresist(?:ance|ant)\b", r"\bantimicrobial\b", r"\bpatient-reported\b",
    r"\bprom\b", r"\brasch\b", r"\bquality of life\b", r"\bdyspn(?:ea|oea)\b",
    r"\bstroke\b", r"\bdiagnos(?:is|tic)\b", r"\bdifferentiat(?:e|ing|ion)\b",
    r"\bindicator of\b", r"\bscreening\b", r"\bobservational study\b",
    r"\bprospective study\b", r"\bretrospective (?:cohort|study|analysis)\b",
    r"\bmixed-methods\b", r"\bqualitative\b", r"\bimpact of\b", r"\beffect of\b",
    r"\bcare (?:process|pathway|bundle)\b", r"\bclinical (?:practice|utility|course|deterioration)\b",
    r"\bcorrelat", r"\bassociated with\b", r"\bapplication of\b", r"\bfrequency of\b",
    r"\bimplementation of\b",
    r"\bassociation (?:between|with)\b", r"\bend[- ]of[- ]life\b", r"\btraining with\b",
    r"\bhand[- ]hygiene\b", r"\binfection control\b", r"\badherence\b",
)
#: Title-level clinical prediction of a clinical target - the paper's object is a clinical
#: decision, not the device. This must beat a measurement noun in the title.
CLINICAL_TARGET = _rx(
    r"\bmortality\b", r"\bmorbidity\b", r"\bdelirium\b", r"\bsepsis\b",
    r"\breadmission\b", r"\blength of stay\b", r"\bweaning\b", r"\bextubation\b",
    r"\borgan failure\b", r"\bheart failure\b", r"\bbnp\b",
    r"\bnt-probnp\b", r"\bbiomarker", r"\bresist(?:ance|ant)\b", r"\bnausea\b",
    r"\bvomiting\b", r"\bdeath\b", r"\bsurvival\b", r"\bcomplication",
    r"\bhypotension\b", r"\bhyper(?:tension|glyc)emia\b", r"\banaemia\b", r"\banemia\b",
    r"\bconcentrations?\b", r"\bexposure\b", r"\bmalnutrition\b", r"\bfrailty\b",
    r"\bpneumonia\b", r"\binfection\b", r"\bbactera?emia\b", r"\bacute kidney injury\b",
    r"\breference (?:values|ranges|intervals)\b", r"\bbilirubin\b", r"\bjaundice\b",
    r"\bha?emorrhage\b", r"\bbleeding\b", r"\bventilator-associated\b",
)
#: Data-science method benchmarking on monitoring data (transfer, not a monitoring device).
DATA_SCIENCE_METHODS = _rx(
    r"\barima\b", r"\bvar model\b", r"\blstm\b", r"\bgru\b", r"\bann\b",
    r"\bbenchmark(?:ing)?\b", r"\btime[- ]series (?:prediction|forecasting)\b",
    r"\bmultivariate (?:healthcare|physiological) time[- ]series\b",
)
#: A strict technology-evaluation vocabulary. Its presence in the title means the record evaluates
#: the measurement itself, which outranks a clinical-application framing.
STRICT_EVALUATION = _rx(
    r"\baccuracy\b", r"\bagreement\b", r"\bvalidation\b", r"\bvalidated\b", r"\bcalibration\b",
    r"\bsignal quality\b", r"\bbench (?:test|study|evaluation)\b", r"\bbias\b",
    r"\bdiscrepan", r"\bconcordance\b", r"\breproducib", r"\bhead-to-head\b",
    r"\bbland[- ]altman\b", r"\bcomparison (?:with|against|of) (?:the )?reference\b",
    r"\bperformance (?:evaluation|comparison|of the)\b",
)
#: IT security / data-protection architecture. It is adjacent engineering, not a monitoring
#: measurement, so it is recorded as TRANSFER and kept out of the default feed.
SECURITY_ARCHITECTURE = _rx(
    r"\bzero[- ]trust\b", r"\bintrusion detection\b", r"\bcyber ?security\b", r"\bencryption\b",
    r"\bauthentication\b", r"\bblockchain\b", r"\bprivacy[- ]preserving\b",
    r"\bsecurity (?:architecture|framework|scheme)\b", r"\bthreat detection\b",
    r"\baccess control\b", r"\bmalware\b", r"\bspoofing\b", r"\bdenial[- ]of[- ]service\b",
)
#: Non-medical subject domains. Only subject text may raise these (never venue or entity text).
NON_MEDICAL_DOMAIN = _rx(
    r"\bsmart grid\b", r"\bpower grid\b", r"\belectrical (?:grid|infrastructure)\b",
    r"\bstructural health\b", r"\bindustrial\b", r"\bmanufacturing\b", r"\bmining\b",
    r"\bvehicular\b", r"\bautomotive\b", r"\bautonomous (?:robots|vehicles|driving)\b",
    r"\bodometry\b", r"\bradar (?:odometry|imaging|target|signal|sensor)\b",
    r"\btarget detection\b", r"\bclutter\b", r"\bcfar\b", r"\bmulti-target\b",
    r"\bdrone\b", r"\buav\b", r"\bunmanned (?:aerial|systems?)\b", r"\baerospace\b",
    r"\baircraft\b", r"\bavionics\b", r"\bsatellite\b", r"\bantenna\b",
    r"\btelecommunication", r"\bwireless (?:communication|channel|network)s?\b",
    r"\b5g\b", r"\b6g\b", r"\bofdm\b", r"\binterference (?:suppression|mitigation)\b",
    r"\bnetwork (?:monitoring|intrusion|security)\b", r"\bserver monitoring\b",
    r"\bcyber[- ]?physical\b", r"\bgravitational[- ]wave\b", r"\binterferometer\b",
    r"\bligo\b", r"\bparticle (?:accelerator|detector)\b",
    r"\bgear(?:box)? (?:health|fault|diagnosis)\b", r"\bbearing (?:fault|health)\b",
    r"\brotating machinery\b", r"\bturbine\b", r"\boil (?:leak|rig|pipeline|spill)\b",
    r"\bpipeline (?:leak|monitoring|integrity)\b", r"\bwater quality\b", r"\bair quality\b",
    r"\bsoil\b", r"\bagricultur", r"\bclimate\b", r"\btraffic monitoring\b",
    r"\brenewable energ", r"\benergy sector\b", r"\bnuclear\b", r"\bradiation monitor",
    r"\bmilitary\b", r"\bweapon\b", r"\bunderwater\b", r"\bsurveillance (?:radar|system)\b",
    r"\bfalse data injection\b", r"\bwireless sensor network",
)
#: A subject term that anchors the record in patient care. Used to keep a non-medical-looking
#: technology that is explicitly applied to patients (radar vital-sign sensing) out of exclusion.
MEDICAL_ANCHOR = _rx(
    r"\bpatients?\b", r"\bclinical\b", r"\bhospital", r"\bicu\b", r"\bintensive care\b",
    r"\bcritical care\b", r"\bmedical\b", r"\bdiagnos", r"\btherap", r"\bnurs(?:e|es|ing)\b",
    r"\bphysician", r"\bvital signs?\b", r"\bphysiolog", r"\bhuman\b",
    r"\bneonat", r"\bpaediatric", r"\bpediatric", r"\bsurgical\b", r"\banaesthesia\b",
    r"\banesthesia\b",
)
#: An explicit statement that a non-monitoring technology is applied to patient monitoring.
TRANSFER_BRIDGE = _rx(
    r"for (?:patient|clinical|vital[- ]sign|medical) monitoring\b",
    r"vital[- ]signs? (?:monitoring|sensing|detection|measurement)\b",
    r"(?:patient|clinical|medical) (?:monitoring|sensing|application)\b",
    r"(?:bedside|continuous) (?:patient )?monitoring\b",
    r"monitoring (?:patients|patient status|vital signs)\b",
)
#: Behaviour/workflow subjects that a wearable or sensor can measure but that are not patient
#: physiological monitoring. They are clinical/service research, not monitoring technology.
NON_PHYSIOLOGICAL_SUBJECT = _rx(
    r"\bhand[- ]hygiene\b", r"\binfection control\b", r"\bstaff (?:adherence|compliance)\b",
    r"\bworkflow\b", r"\bhand ?washing\b", r"\bpersonal protective equipment\b",
    r"\bcontact tracing\b", r"\bmedication adherence\b",
)
SETTING = _rx(
    r"\bicu\b", r"\bintensive care\b", r"\bcritical care\b", r"\bnicu\b", r"\bpicu\b",
    r"\boperating room\b", r"\bemergency department\b", r"\bperioperative\b",
    r"\bward\b", r"\bpostoperative\b", r"\banaesthesia\b", r"\banesthesia\b",
)
NON_HUMAN = _rx(
    r"\b(?:horse|horses|equine|canine|feline|veterinary|bovine|poultry|swine|murine|rodent)\b",
    r"\banimal model\b", r"\bmice\b", r"\brats\b",
)
CASE_VIGNETTE = _rx(r"^\s*[A-Z]\d{1,3}-\d{1,3}\b", r"\bcase report\b", r"\ba false alarm\b",
                    r"\brare cause\b", r"\bunmasking\b", r"\bunmasks\b", r"\bin a patient with\b")
EDITORIAL = _rx(r"^\s*(?:editorial|commentary|comment|letter|erratum|correction|retraction)\b",
                r"\bretraction notice\b")
HEALTH_ECONOMICS = _rx(r"\bcost[- ]effectiveness\b", r"\bcost[- ]benefit\b", r"\bbudget impact\b",
                       r"\bhealth economic", r"\beconomic evaluation\b", r"\bcost[- ]utility\b",
                       r"\bacquisition costs?\b")
MESH_POSITIVE = _rx(
    r"equipment design", r"instrumentation", r"physiologic monitoring", r"signal processing",
    r"algorithms", r"equipment failure analysis", r"monitoring, physiologic",
    r"electrocardiography", r"diagnostic techniques, cardiovascular", r"computers",
)
MESH_NEGATIVE = _rx(
    r"risk assessment", r"treatment outcome", r"retrospective studies",
    r"surveys and questionnaires", r"quality of life", r"cohort studies", r"prognosis",
    r"risk factors",
)
ENGINEERING_VENUE = _rx(
    r"biomedical engineering", r"instrumentation", r"signal processing", r"medical informatics",
    r"health informatics", r"biotechnology", r"electrical engineering",
)
RECALL_TERMS = _rx(r"\brecall\b", r"\bremoval\b", r"\bclass i\b", r"\bsafety (?:alert|notice)\b",
                   r"\bfield safety\b", r"\bdevice failure\b", r"\bcorrection\b")


# --------------------------------------------------------------------------- shape
@dataclass(frozen=True)
class Admission:
    """The decision for one observation. Kept as a dataclass so the ledger and API are unchanged."""

    tier: str
    category: str
    score: float
    reasons: list[str] = field(default_factory=list)
    features: dict[str, Any] = field(default_factory=dict)
    decision: str = DECISION_EXCLUDED
    dimensions: dict[str, Any] = field(default_factory=dict)

    def as_row(self) -> dict[str, Any]:
        return {
            "tier": self.tier,
            "category": self.category,
            "score": self.score,
            "reasons": json.dumps(self.reasons, ensure_ascii=False),
            "features": json.dumps(self.features, ensure_ascii=False),
            "decision": self.decision,
            "dimensions": json.dumps(self.dimensions, ensure_ascii=False, sort_keys=True),
        }


def rules_digest() -> str:
    """A digest of the vocabulary and policy, stored with each decision for reproducibility."""
    material = "|".join((
        ASSESSMENT_VERSION, RULES_VERSION,
        DEVICE_STRONG.pattern, MEASUREMENT_STRONG.pattern, ENGINEERING.pattern,
        EVALUATION.pattern, CLINICAL_APPLICATION.pattern, CLINICAL_TARGET.pattern,
        NON_MEDICAL_DOMAIN.pattern, MEDICAL_ANCHOR.pattern,
    ))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


# --------------------------------------------------------------------------- helpers
def _hits(pattern: re.Pattern[str], text: str) -> int:
    return len(pattern.findall(text or ""))


def _clean(text: str | None) -> str:
    if not text:
        return ""
    plain = re.sub(r"<[^>]+>", " ", str(text))
    plain = re.sub(r"[\u2010-\u2015\u2212\u00a0]", lambda m: "-" if m.group(0) != "\u00a0" else " ", plain)
    return re.sub(r"\s+", " ", plain).strip()


def _payload_text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if value is None:
        inner = payload.get("payload")
        if isinstance(inner, Mapping):
            value = inner.get(key)
    if isinstance(value, (list, tuple)):
        return " ".join(str(item) for item in value)
    return str(value or "")


def subject_text(title: str | None, payload: Mapping[str, Any]) -> str:
    """The record's own statement of what it is about: title, abstract, official summary."""
    return " \n ".join(part for part in (
        _clean(title),
        _clean(_payload_text(payload, "abstract")),
        _clean(_payload_text(payload, "summary")),
        _clean(_payload_text(payload, "description")),
        _clean(_payload_text(payload, "statement_or_summary")),
        _clean(_payload_text(payload, "ao_statement")),
    ) if part)


def venue_text(payload: Mapping[str, Any]) -> str:
    return _clean(_payload_text(payload, "journal") or _payload_text(payload, "container_title"))


def index_text(payload: Mapping[str, Any]) -> str:
    parts = []
    terms = payload.get("mesh_terms")
    if isinstance(terms, (list, tuple)):
        parts.extend(str(term) for term in terms)
    subject = payload.get("subject")
    if isinstance(subject, (list, tuple)):
        parts.extend(str(item) for item in subject)
    return " ".join(parts)


def _precision_of(value: str | None, stated: str | None = None) -> str:
    # A stored label can understate the value it accompanies (a YYYY-MM value stored as
    # "year"). Freshness is graded from the earliest instant the date can denote, so an
    # understated label makes a recent record look old and depresses its grade. The value
    # wins when it is more specific; it can only sharpen the claim.
    label = str(stated or "").strip()
    if label not in ("", "unknown"):
        return effective_precision(value, label)
    if not value:
        return "unknown"
    text = str(value)
    if re.match(r"^\d{4}$", text):
        return "year"
    if re.match(r"^\d{4}-\d{2}$", text):
        return "month"
    if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        return "date"
    return "datetime"


def _freshness(stamp: str | None, precision: str, now: datetime | None) -> str:
    """Freshness uses the earliest instant a precision-limited date can denote.

    A month-precision date is an interval; treating it as its first day is the conservative
    choice for a "is this new?" question, because the record cannot be older than that.
    """
    if not stamp or now is None:
        return FRESHNESS_UNKNOWN
    text = str(stamp)
    try:
        if precision == "year":
            moment = datetime(int(text[:4]), 1, 1, tzinfo=timezone.utc)
        elif precision == "month":
            moment = datetime(int(text[:4]), int(text[5:7]), 1, tzinfo=timezone.utc)
        elif precision == "date":
            moment = datetime(int(text[:4]), int(text[5:7]), int(text[8:10]), tzinfo=timezone.utc)
        else:
            moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return FRESHNESS_UNKNOWN
    age = now - moment
    if age <= timedelta(days=30):
        return FRESH
    if age <= timedelta(days=365):
        return RECENT
    return STALE


def _role_entity_link(record_type: str, organization_role: str | None,
                      mapped_products: Sequence[str] | None) -> str:
    role = str(organization_role or "").strip()
    if role == "regulatory_applicant":
        return ENTITY_APPLICANT
    if role == "official_publisher":
        return ENTITY_VENDOR
    if role == "publication_affiliation":
        return ENTITY_AFFILIATION
    if mapped_products:
        return ENTITY_AFFILIATION
    return ENTITY_NONE


def _source_authenticity(record_type: str) -> str:
    if record_type == "regulatory_record":
        return PRIMARY_REGULATORY
    if record_type in ("press_release", "product_document"):
        return OFFICIAL_VENDOR
    if record_type in ("publication", "clinical_trial"):
        return SCHOLARLY
    return SECONDARY


def _device_family_topics(mapped_topics: Sequence[str] | None, taxonomy: Any | None) -> list[str]:
    if not mapped_topics or taxonomy is None:
        return []
    families = {"electrocardiography", "oxygenation", "haemodynamics", "ventilation", "alarms", "platform"}
    found = []
    for topic_id in mapped_topics:
        topic = None
        try:
            topic = taxonomy.topic(str(topic_id))
        except Exception:  # noqa: BLE001 - a taxonomy lookup must never break admission
            topic = None
        family = getattr(topic, "family", None)
        if family in families or str(topic_id) in DEVICE_TOPICS:
            found.append(str(topic_id))
    return found


def _registry_loaded() -> Any | None:
    from .taxonomy import load_taxonomy

    try:
        return load_taxonomy()
    except Exception:  # noqa: BLE001 - assessment degrades to vocabulary-only judgement
        return None


# --------------------------------------------------------------------- safety grading
#: Language an official reason for recall uses when the failure can reach the patient. It is the
#: only signal that lifts a confirmed recall from HIGH to CRITICAL, and the matched phrase is
#: quoted in the recorded reason instead of being asserted.
HARM_SIGNAL = _rx(
    r"\bcould (?:cause|result in|lead to)\b", r"\bmay (?:cause|result in|lead to)\b",
    r"\bpotential(?:ly)? (?:for )?(?:serious|fatal|harm|injury)\b", r"\bpatient harm\b",
    r"\bserious (?:injury|adverse event|patient injury)\b", r"\bdeath\b", r"\bfatal\b",
    r"\bloss of (?:monitoring|connectivity|alarm|data)\b",
    r"\bfail(?:s|ed|ure)? to (?:alarm|alert|monitor|display)\b",
    r"\bno (?:audible )?(?:alarm|alert|notification)\b",
    r"\bdelay(?:ed)? (?:in )?(?:treatment|therapy|diagnosis|care)\b",
    r"\binaccurate (?:reading|measurement|value|result|data|display)s?\b",
    r"\bincorrect (?:reading|measurement|value|result|data|display|parameter)s?\b",
    r"\b(?:may|can|could) (?:display|report|show) (?:an? )?(?:incorrect|inaccurate|wrong)\b",
    r"\bfreez(?:e|es|ing)\b", r"\block(?:s|ed|ing)? ?up\b",
    r"\bunresponsive (?:screen|display|device|monitor|system)\b",
    r"\bmiss(?:ed|es)? (?:an? )?(?:alarm|arrhythmia|alert|event|desaturation)\b",
    r"\bwrong (?:patient|value|reading|data)\b",
    r"\bnot (?:meet|comply with)\b.{0,40}\bperformance standard\b",
)
#: A title that states a review, a commentary or a perspective is not primary evidence. It is still
#: admissible (a systematic review of NIBP accuracy is genuinely valuable), but a narrative review
#: cannot reach HIGH on the strength of the word "accuracy" in its title.
REVIEW_NOT_PRIMARY = _rx(
    r"\bnarrative review\b", r"\bperspective\b", r"\bcommentary\b", r"\bviewpoint\b",
    r"\beditorial\b", r"\bbeyond\b", r"\boverview\b",
)
PRIMARY_SYNTHESIS = _rx(r"\bsystematic review\b", r"\bmeta-?analysis\b", r"\bscoping review\b")
#: A study design too weak to support "this changes how you verify your device": one patient, a
#: case report, a case series. It caps the grade instead of excluding the record.
WEAK_DESIGN = _rx(
    r"\bsingle[- ]patient\b", r"\bcase (?:study|series|report)\b", r"\bn\s*=\s*1\b",
    r"\bsingle[- ]centre feasibility\b",
)


# --------------------------------------------------------------------- safety grading
_IMPORTANCE_RANK = {
    IMPORTANCE_CRITICAL: 0,
    IMPORTANCE_HIGH: 1,
    IMPORTANCE_MEDIUM: 2,
    IMPORTANCE_LOW: 3,
}


def merge_importance(graded: str, declared: str | None) -> str:
    """The graded level, with one veto a decision branch is allowed to keep.

    A branch that has positively identified a non-intelligence record (a case vignette, an
    animal study, an editorial notice) may say LOW, and that veto holds. A branch may NOT raise
    a level: doing so would let a template override staleness and evidence strength, which is
    exactly how the previous round ended up with 8,590 MEDIUM out of 8,593.
    """
    if declared == IMPORTANCE_LOW:
        return IMPORTANCE_LOW
    return graded


def _safety_text(payload: Mapping[str, Any]) -> str:
    """The source's own statement of what went wrong (not our summary of it)."""
    return " ".join(str(payload.get(field) or "") for field in
                    ("product_description", "reason_for_recall", "action", "root_cause_description"))


def _device_class(payload: Mapping[str, Any]) -> str | None:
    """The FDA device class the endpoint states for the recall row, when it states one."""
    official = payload.get("openfda_device")
    if not isinstance(official, Mapping):
        return None
    value = str(official.get("device_class") or "").strip()
    return value or None


def grade_importance(
    *,
    record_type: str,
    category: str,
    decision: str,
    relevance: str | None = None,
    freshness: str | None = None,
    payload: Mapping[str, Any] | None = None,
    recall_verdict: Mapping[str, Any] | None = None,
    strict_evaluation: bool = False,
    title: str | None = None,
) -> tuple[str, list[str]]:
    """Grade one record CRITICAL / HIGH / MEDIUM / LOW and say exactly why.

    The rules are ordered and each returns its reasons, so a reader can check the grade instead
    of trusting it. Nothing is quota-driven: a quiet week can be all LOW and a bad week can hold
    three CRITICALs.

    CRITICAL  a still-open safety action on a monitoring device whose official reason states a
              patient-safety consequence (loss of monitoring, failed alarm, incorrect value,
              freezing, harm), or an FDA class-1 action on a monitoring device.
    HIGH      a still-open safety action on a monitoring device without a stated consequence; or
              fresh evidence that evaluates the measurement itself (accuracy/agreement/bias).
    MEDIUM    a monitored-device regulatory decision in the last 12 months, a direct monitoring
              record published in the last 12 months, or a recent record that still needs review.
    LOW       everything else, including historical archive and out-of-scope records.
    """
    payload = dict(payload or {})
    reasons: list[str] = []
    status = str(payload.get("recall_status") or "").strip()
    terminated = status.lower().startswith("terminated")
    device_class = _device_class(payload)
    recall = recall_verdict if recall_verdict is not None else None
    in_scope_recall = bool(recall and recall.get("in_scope"))

    if in_scope_recall:
        reasons.append(str(recall.get("reason") or "a safety action on a monitoring device"))
        text = _safety_text(payload)
        matches = sorted({match.group(0).lower() for match in HARM_SIGNAL.finditer(text)})
        if terminated:
            reasons.append("the action is recorded as terminated (" + (status or "unknown") + ")")
        else:
            reasons.append("the action is still open (" + (status or "status not stated") + ")")
        if matches and not terminated:
            reasons.append(
                "the official reason states a potential patient-safety consequence: "
                + ", ".join(matches[:3])
            )
            if device_class == "1":
                reasons.append("FDA device class 1")
            return IMPORTANCE_CRITICAL, reasons
        if device_class == "1" and not terminated:
            reasons.append("FDA device class 1 action on a monitoring device")
            return IMPORTANCE_CRITICAL, reasons
        reasons.append("the official reason states no patient-safety consequence of its own")
        return (IMPORTANCE_MEDIUM if terminated else IMPORTANCE_HIGH), reasons

    if recall is not None and not recall.get("in_scope"):
        return IMPORTANCE_LOW, [str(recall.get("reason") or "not a monitoring device")]

    title_text = str(title or "")
    weak = bool(WEAK_DESIGN.search(title_text))
    review_piece = bool(REVIEW_NOT_PRIMARY.search(title_text)) and not bool(
        PRIMARY_SYNTHESIS.search(title_text))
    if (relevance == DIRECT and freshness == FRESH and strict_evaluation and not weak
            and not review_piece):
        return IMPORTANCE_HIGH, [
            "monitoring technology is the subject of the record",
            "the record evaluates the measurement itself (accuracy/agreement/validation)",
            "the source-stated date is within the last 30 days",
        ]
    if relevance == DIRECT and freshness == FRESH and strict_evaluation and weak:
        return IMPORTANCE_MEDIUM, [
            "the record evaluates the measurement itself",
            "but the stated design is one patient or a case report, so it cannot carry a HIGH",
            "the source-stated date is within the last 30 days",
        ]
    if relevance == DIRECT and freshness == FRESH and strict_evaluation and review_piece:
        return IMPORTANCE_MEDIUM, [
            "the record evaluates the measurement itself",
            "but the title states a review, commentary or perspective, not a primary study",
            "the source-stated date is within the last 30 days",
        ]
    if record_type == "regulatory_record" and relevance == DIRECT and freshness in (FRESH, RECENT):
        return IMPORTANCE_MEDIUM, [
            "a regulatory decision for a monitored device family",
            "the official decision date is within the last 12 months",
        ]
    if relevance == DIRECT and freshness in (FRESH, RECENT):
        return IMPORTANCE_MEDIUM, [
            "monitoring technology is the subject of the record",
            "the source-stated date is within the last 12 months",
        ]
    if decision == DECISION_REVIEW and freshness in (FRESH, RECENT):
        return IMPORTANCE_MEDIUM, [
            "the record needs a reviewer to classify it",
            "the source-stated date is within the last 12 months",
        ]
    if freshness in (STALE, FRESHNESS_UNKNOWN):
        return IMPORTANCE_LOW, [
            "historical archive: the source-stated date is older than 12 months or not stated",
        ]
    return IMPORTANCE_LOW, ["not a monitoring-technology record for the default brief"]


# --------------------------------------------------------------------------- assessment
@dataclass(frozen=True)
class _Signals:
    title: str
    subject: str
    venue: str
    index: str
    title_device: int
    title_measurement: int
    title_engineering: int
    title_evaluation: int
    subject_device: int
    subject_measurement: int
    subject_engineering: int
    subject_evaluation: int
    clinical_application: int
    clinical_target: int
    non_medical: int
    medical_anchor: int
    transfer_bridge: int
    setting: int
    mesh_positive: int
    mesh_negative: int
    engineering_venue: int
    data_science: int
    title_clinical_application: int
    title_strict_evaluation: int
    title_security: int
    title_transfer_bridge: int
    device_family_topics: tuple[str, ...]
    has_abstract: bool


def _signals(title: str, payload: Mapping[str, Any], mapped_topics: Sequence[str] | None,
             taxonomy: Any | None) -> _Signals:
    clean_title = _clean(title)
    subject = subject_text(title, payload)
    venue = venue_text(payload)
    index = index_text(payload)
    abstract = _clean(_payload_text(payload, "abstract"))
    return _Signals(
        title=clean_title,
        subject=subject,
        venue=venue,
        index=index,
        title_device=_hits(DEVICE_STRONG, clean_title),
        title_measurement=_hits(MEASUREMENT_STRONG, clean_title),
        title_engineering=_hits(ENGINEERING, clean_title),
        title_evaluation=_hits(EVALUATION, clean_title),
        subject_device=_hits(DEVICE_STRONG, subject),
        subject_measurement=_hits(MEASUREMENT_STRONG, subject),
        subject_engineering=_hits(ENGINEERING, subject),
        subject_evaluation=_hits(EVALUATION, subject),
        clinical_application=_hits(CLINICAL_APPLICATION, subject),
        clinical_target=_hits(CLINICAL_TARGET, clean_title),
        non_medical=_hits(NON_MEDICAL_DOMAIN, subject),
        medical_anchor=_hits(MEDICAL_ANCHOR, subject),
        transfer_bridge=_hits(TRANSFER_BRIDGE, subject),
        setting=_hits(SETTING, subject),
        mesh_positive=_hits(MESH_POSITIVE, index),
        mesh_negative=_hits(MESH_NEGATIVE, index),
        engineering_venue=_hits(ENGINEERING_VENUE, venue),
        data_science=_hits(DATA_SCIENCE_METHODS, subject),
        title_clinical_application=_hits(CLINICAL_APPLICATION, clean_title),
        title_strict_evaluation=_hits(STRICT_EVALUATION, clean_title),
        title_security=_hits(SECURITY_ARCHITECTURE, clean_title),
        title_transfer_bridge=_hits(TRANSFER_BRIDGE, clean_title),
        device_family_topics=tuple(_device_family_topics(mapped_topics, taxonomy)),
        has_abstract=len(abstract) > 120,
    )


def _monitoring_subject(signals: _Signals) -> tuple[bool, str]:
    """Is the record's own subject a monitoring technology, a measurement or its engineering?"""
    if signals.title_device:
        return True, "title names a monitoring device"
    if signals.title_measurement:
        # A measurement noun plus any evaluation/engineering signal, a care setting, or an
        # explicit monitoring phrase is a monitoring-technology subject. A measurement noun
        # alone in a clinical prediction title is handled by the clinical branch first.
        if signals.title_evaluation or signals.title_engineering or signals.setting:
            return True, "title names a monitoring measurement with an evaluation/engineering signal"
        if re.search(r"\bmonitoring\b", signals.title, re.IGNORECASE):
            return True, "title names a monitoring measurement"
        if signals.subject_evaluation or signals.subject_engineering:
            return True, "title names a monitoring measurement studied in the abstract"
    return False, ""


def _non_medical_subject(signals: _Signals) -> bool:
    if signals.non_medical < 1:
        return False
    if signals.medical_anchor >= 2:
        return False
    if signals.title_device or signals.title_measurement:
        return False
    return True


def assess_publication(*, title: str | None, payload: Mapping[str, Any] | None = None,
                       mapped_topics: Sequence[str] | None = None,
                       mapped_products: Sequence[str] | None = None,
                       taxonomy: Any | None = None,
                       freshness: str | None = None) -> Admission:
    payload = dict(payload or {})
    registry = taxonomy if taxonomy is not None else _registry_loaded()
    signals = _signals(str(title or payload.get("title") or ""), payload, mapped_topics, registry)
    features = {
        "has_abstract": signals.has_abstract,
        "title_device": signals.title_device,
        "title_measurement": signals.title_measurement,
        "title_engineering": signals.title_engineering,
        "title_evaluation": signals.title_evaluation,
        "subject_device": signals.subject_device,
        "subject_measurement": signals.subject_measurement,
        "subject_engineering": signals.subject_engineering,
        "subject_evaluation": signals.subject_evaluation,
        "clinical_application": signals.clinical_application,
        "clinical_target": signals.clinical_target,
        "non_medical": signals.non_medical,
        "medical_anchor": signals.medical_anchor,
        "transfer_bridge": signals.transfer_bridge,
        "setting": signals.setting,
        "mesh_positive": signals.mesh_positive,
        "mesh_negative": signals.mesh_negative,
        "engineering_venue": signals.engineering_venue,
        "data_science_methods": signals.data_science,
        "device_family_topics": list(signals.device_family_topics),
        "title_clinical_application": signals.title_clinical_application,
        "title_strict_evaluation": signals.title_strict_evaluation,
        "title_security_architecture": signals.title_security,
        "title_transfer_bridge": signals.title_transfer_bridge,
        "journal_is_not_subject_evidence": True,
    }

    def decide(relevance: str, domain: str, category: str, score: float, reasons: list[str],
               importance: str | None = None, confidence: float = 0.7) -> Admission:
        if relevance == DIRECT:
            tier, decision = HIGH_RELEVANCE, DECISION_FEED
        elif relevance == TRANSFER:
            # A transfer enters the default feed only when the title itself states the
            # patient-monitoring purpose. An abstract mention is not a purpose statement.
            if signals.title_transfer_bridge and signals.medical_anchor:
                tier, decision, category = HIGH_RELEVANCE, DECISION_FEED, category + "_transfer"
            else:
                tier, decision = NEEDS_REVIEW, DECISION_REVIEW
        elif relevance == CLINICAL:
            tier, decision = LOW_RELEVANCE, DECISION_EXCLUDED
        elif relevance == MEDICAL_UNRELATED:
            tier, decision = LOW_RELEVANCE, DECISION_EXCLUDED
        else:
            tier, decision = IRRELEVANT, DECISION_EXCLUDED
        level, why = grade_importance(
            record_type="publication",
            category=category,
            decision=decision,
            relevance=relevance,
            freshness=freshness,
            payload=payload,
            strict_evaluation=bool(signals.title_strict_evaluation),
            title=title,
        )
        dimensions = {
            "source_authenticity": SCHOLARLY,
            "medical_domain": domain,
            "monitoring_relevance": relevance,
            "entity_link": _role_entity_link("publication", None, mapped_products),
            "freshness": freshness or FRESHNESS_UNKNOWN,
            "importance": merge_importance(level, importance),
            "importance_reasons": why,
            "confidence": round(confidence, 2),
            "decision": decision,
        }
        if not signals.has_abstract and "no abstract" not in " ".join(reasons):
            # Say so in the decision rather than letting a title-only judgement look complete.
            reasons = [*reasons, "no abstract: judged from the title only"]
            dimensions["confidence"] = round(max(0.2, confidence - 0.1), 2)
        return Admission(tier, category, round(score, 2), reasons, features, decision, dimensions)

    # 1. Subjects are animals: not patient monitoring.
    if _hits(NON_HUMAN, signals.subject) and not signals.mesh_positive:
        return decide(NON_MEDICAL, NON_MEDICAL, "non_human_subject", -10.0,
                      ["subjects are animals, not patients"], IMPORTANCE_LOW, 0.95)
    # 2. A clearly non-medical domain with no patient anchor.
    if _non_medical_subject(signals):
        return decide(NON_MEDICAL, NON_MEDICAL, "non_medical_domain", -10.0,
                      ["the subject is not a patient (industrial/telecom/energy/other domain)"],
                      IMPORTANCE_LOW, 0.9)
    # 3. Bibliographic notices are not technology evidence.
    if EDITORIAL.search(signals.title):
        return decide(MEDICAL_UNRELATED, MEDICAL, "bibliographic_notice", -6.0,
                      ["editorial/correction/retraction notice, not technology evidence"],
                      IMPORTANCE_LOW, 0.9)
    # 4. Case vignettes.
    if CASE_VIGNETTE.search(signals.title):
        return decide(CLINICAL, MEDICAL, "case_report", -2.0,
                      ["single-case vignette, not monitoring-technology research"], IMPORTANCE_LOW, 0.8)
    # 5. Health economics.
    if HEALTH_ECONOMICS.search(signals.subject):
        return decide(CLINICAL, MEDICAL, "health_economics", -1.0,
                      ["health-economic analysis, not monitoring technology"], IMPORTANCE_LOW, 0.8)

    monitoring, why = _monitoring_subject(signals)
    technology_subject = bool(signals.title_device or signals.title_engineering
                              or signals.title_measurement)

    # 5b. A behaviour/workflow subject is clinical service research even when a sensor measures it.
    if NON_PHYSIOLOGICAL_SUBJECT.search(signals.title):
        return decide(CLINICAL, MEDICAL, "behaviour_or_workflow_monitoring", -1.0,
                      ["sensor measures behaviour/workflow, not patient physiology"],
                      IMPORTANCE_LOW, 0.8)

    # 6. Health-IT security architecture is adjacent engineering, not a monitoring measurement.
    #    It is transferred technology; it is not fed as monitoring intelligence.
    if signals.title_security and not (signals.title_device or signals.title_measurement):
        return decide(TRANSFER, MEDICAL, "security_architecture", 1.0,
                      ["security/data-protection architecture, not monitoring technology"],
                      IMPORTANCE_LOW, 0.7)

    # 7. A structured review of monitoring technology is technology evidence, not clinical use.
    if re.search(r"\b(?:systematic|narrative|scoping|literature) review\b", signals.title, re.IGNORECASE) \
            and (signals.title_measurement or signals.title_device):
        return decide(DIRECT, MEDICAL, "monitoring_technology_review", 4.0,
                      ["structured review whose subject is monitoring technology"],
                      IMPORTANCE_MEDIUM, 0.8)

    # 8. A clinical prediction or correlation of a clinical target is a clinical study even when a
    #    measurement noun appears in the title (a wearable ECG used to predict BNP is not ECG
    #    engineering). A strict evaluation of the measurement itself outranks this.
    if signals.clinical_target and not signals.title_strict_evaluation:
        return decide(CLINICAL, MEDICAL, "clinical_prediction_model", -1.0,
                      ["the object is a clinical target/outcome, not monitoring technology"],
                      IMPORTANCE_LOW, 0.85)

    # 8. Clinical application framing in the title is clinical use, unless the record evaluates
    #    the technology itself (accuracy/agreement/validation) or the title names the device or
    #    the algorithm as the object.
    if signals.title_clinical_application and not signals.title_engineering \
            and not signals.title_strict_evaluation:
        return decide(CLINICAL, MEDICAL, "clinical_application_of_monitoring", -1.0,
                      ["clinical application or care pathway, not monitoring technology itself"],
                      IMPORTANCE_LOW, 0.75)

    # 9. A monitoring subject: the default feed.
    if monitoring:
        device_family = bool(signals.device_family_topics)
        if signals.title_measurement and not signals.title_device and not signals.title_evaluation \
                and not signals.title_engineering and not device_family and not signals.setting:
            return decide(TRANSFER, MEDICAL, "measurement_without_technology_focus", 1.0,
                          ["a measurement is named but not a monitoring technology under study"],
                          IMPORTANCE_LOW, 0.55)
        score = 4.0 + 1.0 * bool(signals.title_evaluation) + 1.0 * bool(signals.title_engineering)
        score += 0.5 * bool(signals.mesh_positive) + 0.5 * bool(signals.engineering_venue)
        reasons = [why]
        if signals.title_evaluation:
            reasons.append("evaluates accuracy/performance/agreement")
        if signals.title_engineering:
            reasons.append("engineering or algorithm is the object")
        if signals.title_clinical_application:
            reasons.append("a clinical-use caveat was overridden by a title-level technology study")
        return decide(DIRECT, MEDICAL, "monitoring_technology_evaluation", score, reasons,
                      IMPORTANCE_MEDIUM,
                      0.9 if (signals.title_device or signals.title_measurement) else 0.7)

    # 10. Data-science methods applied to monitoring data: transfer, not monitoring technology.
    if signals.data_science and signals.medical_anchor:
        return decide(TRANSFER, MEDICAL, "methods_benchmark_on_monitoring_data", 1.5,
                      ["method benchmarking on monitoring data, not a monitoring technology"],
                      IMPORTANCE_LOW, 0.6)

    # 11. Clinical studies that use monitoring data.
    if signals.clinical_application or signals.clinical_target:
        return decide(CLINICAL, MEDICAL, "clinical_study_without_device_focus", -1.0,
                      ["clinical question; monitoring technology is not under study"],
                      IMPORTANCE_LOW, 0.75)

    # 12. Medical but no monitoring subject at all.
    if signals.medical_anchor or signals.mesh_positive or signals.mesh_negative:
        return decide(MEDICAL_UNRELATED, MEDICAL, "medical_not_monitoring", -2.0,
                      ["medical record that does not concern monitoring technology"],
                      IMPORTANCE_LOW, 0.6)
    # 13. Nothing identifiable: a record is never promoted on absence of evidence.
    return decide(MEDICAL_UNRELATED, UNCERTAIN_DOMAIN, "no_monitoring_signal", -3.0,
                  ["no monitoring-technology signal in the subject text"], IMPORTANCE_LOW, 0.4)


def assess_observation(record: Mapping[str, Any], *, mapped_topics: Sequence[str] | None = None,
                       mapped_products: Sequence[str] | None = None,
                       taxonomy: Any | None = None, now: datetime | None = None) -> Admission:
    """Assess one observation row (record_type + title + payload)."""
    record_type = str(record.get("record_type") or "")
    payload_raw = record.get("payload")
    if isinstance(payload_raw, str):
        try:
            payload = json.loads(payload_raw)
        except json.JSONDecodeError:
            payload = {}
    elif isinstance(payload_raw, Mapping):
        payload = dict(payload_raw)
    else:
        payload = {}
    title = str(record.get("title") or payload.get("title") or "")
    registry = taxonomy if taxonomy is not None else _registry_loaded()
    mapped_topics = list(mapped_topics or ())
    mapped_products = list(mapped_products or ())
    signals = _signals(title, payload, mapped_topics, registry)
    published = record.get("published_at")
    event = record.get("event_at")
    precision = _precision_of(
        str(published or event) if (published or event) else None,
        record.get("published_at_precision") or record.get("event_at_precision"),
    )
    freshness = _freshness(str(published or event) if (published or event) else None, precision,
                          now or datetime.now(timezone.utc))
    # A recall is identified by the source's own event number, and screened against the
    # committed taxonomy. The screen is a rule (not stored content), so a later rule version
    # re-judges the row instead of looking like a source correction.
    recall_verdict = None
    if record_type == "regulatory_record" and is_recall_payload(payload):
        recall_verdict = screen_recall(payload, taxonomy=registry)
    recall = bool(RECALL_TERMS.search(signals.subject)) and record_type == "regulatory_record"
    source = _source_authenticity(record_type)
    entity_link = _role_entity_link(record_type, record.get("organization_role"), mapped_products)
    device_family = bool(signals.device_family_topics)
    features = {
        "title_device": signals.title_device,
        "title_measurement": signals.title_measurement,
        "title_engineering": signals.title_engineering,
        "title_evaluation": signals.title_evaluation,
        "device_family_topics": list(signals.device_family_topics),
        "mapped_products": mapped_products[:5],
        "recall_terms": recall,
        "recall_screen": recall_verdict,
        "date_precision": precision,
        "journal_is_not_subject_evidence": True,
    }

    def finish(relevance: str, domain: str, category: str, score: float, reasons: list[str],
               *, decision: str | None = None, confidence: float = 0.8,
               imp: str | None = None) -> Admission:
        if decision is None:
            if relevance == DIRECT:
                decision, tier = DECISION_FEED, HIGH_RELEVANCE
            elif relevance == TRANSFER:
                decision, tier = DECISION_REVIEW, NEEDS_REVIEW
            elif relevance in (CLINICAL, MEDICAL_UNRELATED):
                decision, tier = DECISION_EXCLUDED, LOW_RELEVANCE
            else:
                decision, tier = DECISION_EXCLUDED, IRRELEVANT
        else:
            tier = {
                DECISION_FEED: HIGH_RELEVANCE,
                DECISION_REVIEW: NEEDS_REVIEW,
                DECISION_EXCLUDED: LOW_RELEVANCE,
            }[decision]
        level, why = grade_importance(
            record_type=record_type,
            category=category,
            decision=decision,
            relevance=relevance,
            freshness=freshness,
            payload=payload,
            recall_verdict=recall_verdict,
            strict_evaluation=bool(signals.title_strict_evaluation),
            title=title,
        )
        dimensions = {
            "source_authenticity": source,
            "medical_domain": domain,
            "monitoring_relevance": relevance,
            "entity_link": entity_link,
            "freshness": freshness,
            "importance": merge_importance(level, imp),
            "importance_reasons": why,
            "confidence": round(confidence, 2),
            "decision": decision,
        }
        return Admission(tier, category, round(score, 2), reasons, features, decision, dimensions)

    # ---------------------------------------------------------------- primary records
    if record_type == "regulatory_record":
        if recall_verdict is not None:
            if not recall_verdict["in_scope"]:
                # Stored, excluded, and its reason is kept: a recall feed that silently drops
                # rows is indistinguishable from a feed that missed them.
                return finish(MEDICAL_UNRELATED, MEDICAL, "recall_not_monitoring_device", 0.0,
                              [str(recall_verdict["reason"])], confidence=0.9)
            if recall_verdict["needs_review"]:
                return finish(DIRECT, MEDICAL, "recall_monitoring_device_unconfirmed", 6.0,
                              [str(recall_verdict["reason"]),
                               "the monitoring classification is MedRadar's, not FDA's: a "
                               "reviewer must confirm it"],
                              decision=DECISION_REVIEW, confidence=0.7)
            reasons = [str(recall_verdict["reason"]),
                       "an official FDA safety action on a monitored device"]
            return finish(DIRECT, MEDICAL, "monitoring_safety_action", 9.5, reasons,
                          confidence=0.95)
        if device_family:
            return finish(DIRECT, MEDICAL, "regulatory_monitoring_device", 9.0,
                          ["a primary regulatory record for a monitored device family"],
                          confidence=0.95)
        # A regulatory record outside every monitored device family is not monitoring
        # intelligence, however authentic the source.
        return finish(MEDICAL_UNRELATED, MEDICAL, "regulatory_other_device", 0.0,
                      ["a regulatory record, but not for a monitored device family"],
                      confidence=0.85)
    if record_type in ("press_release", "product_document"):
        monitoring, why = _monitoring_subject(signals)
        if monitoring:
            return finish(DIRECT, MEDICAL, "vendor_statement_monitoring", 8.0,
                          [why, "an official vendor statement about a monitoring product"],
                          confidence=0.9)
        if device_family:
            return finish(DIRECT, MEDICAL, "vendor_statement_monitoring", 6.0,
                          ["a vendor statement mapped to a monitored device family"],
                          confidence=0.7)
        if not mapped_topics and not mapped_products:
            return finish(MEDICAL_UNRELATED, UNCERTAIN_DOMAIN, "primary_record_unmapped", 0.0,
                          ["primary source, but it mentions no monitored product or topic"],
                          confidence=0.8)
        # This is the HyperVue case: an authentic official statement about a product that is not
        # monitoring technology. Source authenticity is not subject judgement.
        return finish(MEDICAL_UNRELATED, MEDICAL, "official_statement_not_monitoring", -1.0,
                      ["official source, but the subject is not monitoring technology"],
                      confidence=0.85)
    if record_type == "publication":
        admission = assess_publication(title=title, payload=payload, mapped_topics=mapped_topics,
                                       mapped_products=mapped_products, taxonomy=registry,
                                       freshness=freshness)
        dimensions = dict(admission.dimensions)
        dimensions.update({
            "source_authenticity": SCHOLARLY,
            "entity_link": entity_link,
            "freshness": freshness,
            "decision": admission.decision,
        })
        # Keep the observation-level facts (date precision, mapped products, recall terms) on the
        # decision, so the publication judgement can be audited from one row.
        merged_features = {**admission.features, **features}
        return Admission(admission.tier, admission.category, admission.score, admission.reasons,
                         merged_features, admission.decision, dimensions)
    # Unknown record types are not promoted on absence of rules.
    return finish(MEDICAL_UNRELATED, UNCERTAIN_DOMAIN, "unclassified_record_type", 0.0,
                  ["record type %r has no qualification rule" % record_type], confidence=0.3)


# --------------------------------------------------------------------------- compatibility
def classify_publication(*, title: str, payload: Mapping[str, Any]) -> Admission:
    """Backward-compatible entry point for one publication record."""
    return assess_publication(title=title, payload=payload)


def classify_observation(record: Mapping[str, Any], *, mapped_topics: Sequence[str] | None = None,
                         mapped_products: Sequence[str] | None = None) -> Admission:
    """Backward-compatible entry point for one observation row."""
    return assess_observation(record, mapped_topics=mapped_topics, mapped_products=mapped_products)


def tier_for_label(label: str) -> str:
    return label


def summarize(admissions: Iterable[Admission]) -> dict[str, int]:
    counts = {tier: 0 for tier in TIER_ORDER}
    for admission in admissions:
        counts[admission.tier] = counts.get(admission.tier, 0) + 1
    return counts


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


__all__ = [
    "ADMISSION_VERSION", "ASSESSMENT_VERSION", "RULES_VERSION", "rules_digest",
    "Admission", "HIGH_RELEVANCE", "NEEDS_REVIEW", "LOW_RELEVANCE", "IRRELEVANT",
    "TIER_ORDER", "TIER_LABELS_ZH", "AUTHORITATIVE_RECORD_TYPES", "PRIMARY_RECORD_TYPES",
    "DECISION_FEED", "DECISION_REVIEW", "DECISION_EXCLUDED", "DECISIONS",
    "DIRECT", "TRANSFER", "CLINICAL", "MEDICAL_UNRELATED", "NON_MEDICAL",
    "IMPORTANCE_CRITICAL", "IMPORTANCE_LEVELS", "IMPORTANCE_VALUES", "grade_importance",
    "merge_importance",
    "MONITORING_RELEVANCE_CLASSES", "DEVICE_FAMILIES", "DEVICE_TOPICS",
    "assess_observation", "assess_publication", "classify_observation",
    "classify_publication", "summarize", "now_iso", "tier_for_label",
    "subject_text", "venue_text", "index_text",
]
