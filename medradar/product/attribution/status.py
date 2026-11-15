"""Attribution verification status: the vocabulary that keeps three claims apart.

PRODUCT-001 had a single boolean-ish field (`review: curated | pending_review`) and the product
reported "attribution share" as if it were accuracy. PRODUCT-002 replaces that with an explicit
status vocabulary in which a *deterministic rule*, *documentary evidence* and *human review* are
different things and can never be silently upgraded into each other.

Statuses (ordered from weakest to strongest claim):

`proposed`
    A spelling that was machine-proposed, or authored as part of the registry, but for which no
    independent verification is recorded. It may be attributed (a working assumption) but must be
    labelled provisional everywhere it is counted.

`rule_verified`
    A deterministic, reproducible rule justifies the acceptance:
      * `name_identity_v1`      - the spelling IS the declared legal name or contains a declared
        brand token as a whole-word sequence (after Unicode NFC + casefold + whitespace collapse);
      * `lexical_equivalence_v1` - the spelling differs from a stronger sibling only by case,
        punctuation or a trailing legal-form token (INC, LLC, GMBH, ...).
    A rule is not a reviewer. `rule_verified` is NOT human review and NOT independent evidence.

`evidence_verified`
    At least one independent documentary source is recorded for this exact decision: a filing
    exhibit, an official registration record, a regulator page or a corporate document, with a
    URL, an access date and the reviewer identity/kind that recorded it.

`human_reviewed`
    A named human reviewer made or confirmed the decision. Only a review-ledger decision whose
    `reviewer_kind` is `human` can produce this status. An AI agent can never award it to itself.

`rejected`
    Reviewed and determined NOT to belong to the organization (a different business, an unrelated
    institution, or a name that only looks similar).

`unresolved`
    Reviewed and not determinable from available evidence. Counted separately, never as verified.

The product reports, separately and explicitly:

* Attributed Share          - records in the collected sample that carry any organization attribution;
* Rule-verified Share       - attributed records whose mapping is justified by a deterministic rule;
* Curated Share             - attributed records whose mapping is evidence-verified or human-reviewed;
* Estimated Attribution     - correctness of a mapping, estimated by an independent sample review;
  Precision                  no independent sample exists -> `UNKNOWN`, never a fabricated number;
* Retrieval Coverage        - share of a known population of relevant records that was retrieved;
  no independent denominator exists -> `UNKNOWN`.

Nothing in this module invents a status: every upgrade is derived from an explicit field
(registry review flag, ownership evidence record, or review-ledger decision) and carries the rule
id or evidence reference that authorised it.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

# ---------------------------------------------------------------------------
# vocabulary
# ---------------------------------------------------------------------------

PROPOSED = "proposed"
RULE_VERIFIED = "rule_verified"
EVIDENCE_VERIFIED = "evidence_verified"
HUMAN_REVIEWED = "human_reviewed"
REJECTED = "rejected"
UNRESOLVED = "unresolved"

#: Every status a *decision* (an accepted or rejected applicant spelling) can have.
DECISION_STATUSES = (PROPOSED, RULE_VERIFIED, EVIDENCE_VERIFIED, HUMAN_REVIEWED, REJECTED, UNRESOLVED)

#: The statuses that justify counting a record as "curated" in the product metrics.
CURATED_STATUSES = frozenset({EVIDENCE_VERIFIED, HUMAN_REVIEWED})

#: Statuses produced by a deterministic rule rather than independent evidence.
RULE_STATUSES = frozenset({RULE_VERIFIED})

#: Statuses that are still a working assumption.
PROVISIONAL_STATUSES = frozenset({PROPOSED, UNRESOLVED})

STATUS_RANK = {
    PROPOSED: 0,
    UNRESOLVED: 1,
    RULE_VERIFIED: 2,
    EVIDENCE_VERIFIED: 3,
    HUMAN_REVIEWED: 4,
    REJECTED: 5,
}

STATUS_LABELS_EN = {
    PROPOSED: "proposed (provisional)",
    RULE_VERIFIED: "rule-verified (deterministic rule, not human review)",
    EVIDENCE_VERIFIED: "evidence-verified (independent source recorded)",
    HUMAN_REVIEWED: "human-reviewed",
    REJECTED: "rejected",
    UNRESOLVED: "unresolved (cannot determine)",
}

STATUS_LABELS_ZH = {
    PROPOSED: "机器提议（暂定归属）",
    RULE_VERIFIED: "规则校验（确定性规则，非人工复核）",
    EVIDENCE_VERIFIED: "证据核验（已记录独立来源）",
    HUMAN_REVIEWED: "人工复核",
    REJECTED: "已驳回",
    UNRESOLVED: "无法判断",
}

STATUS_MEANINGS_EN = {
    PROPOSED: "Attributed as a working assumption. No independent verification is recorded; counts that depend on this mapping are provisional.",
    RULE_VERIFIED: "A deterministic, reproducible name rule justifies the acceptance. A rule is not a reviewer and this is not human review.",
    EVIDENCE_VERIFIED: "An independent documentary source is recorded for this decision. An agent may have collected the evidence; the record states who and what.",
    HUMAN_REVIEWED: "A named human reviewer made or confirmed this decision.",
    REJECTED: "Rejected: the spelling belongs to a different business or entity.",
    UNRESOLVED: "Reviewed but not determinable from the recorded evidence.",
}

#: Rule identifiers. A status upgrade always names the rule that authorised it.
RULE_NAME_IDENTITY = "name_identity_v1"
RULE_LEXICAL_EQUIVALENCE = "lexical_equivalence_v1"
RULE_OWNERSHIP_EVIDENCE = "ownership_evidence_v1"
RULE_REGISTRY_AUTHORING = "registry_authoring_v1"
RULE_MACHINE_PROPOSAL = "token_scope_proposal_v1"
RULE_REVIEW_LEDGER = "review_ledger_v1"

RULE_LABELS = {
    RULE_NAME_IDENTITY: "spelling is the declared legal name or contains a declared brand token as a whole-word sequence",
    RULE_LEXICAL_EQUIVALENCE: "spelling differs from a stronger sibling only by case, punctuation or legal-form suffix",
    RULE_OWNERSHIP_EVIDENCE: "ownership/name relation recorded with an independent source and effective dates",
    RULE_REGISTRY_AUTHORING: "spelling authored with the organization registry; no verification recorded",
    RULE_MACHINE_PROPOSAL: "spelling proposed by the collection-scope token rule; no review recorded",
    RULE_REVIEW_LEDGER: "decision recorded in the internal identity review ledger",
}

REVIEWER_KINDS = ("human", "agent")


def is_curated(status: str | None) -> bool:
    return status in CURATED_STATUSES


def is_rule_verified(status: str | None) -> bool:
    return status in RULE_STATUSES


def is_provisional(status: str | None) -> bool:
    return status in PROVISIONAL_STATUSES


# ---------------------------------------------------------------------------
# deterministic name rules
# ---------------------------------------------------------------------------

#: Trailing legal forms that may be dropped when deciding lexical equivalence.
LEGAL_FORM_TOKENS = (
    "inc",
    "incorporated",
    "corp",
    "corporation",
    "co",
    "company",
    "llc",
    "llp",
    "lp",
    "plc",
    "ltd",
    "limited",
    "gmbh",
    "ag",
    "kg",
    "kgaa",
    "sa",
    "sas",
    "sarl",
    "bv",
    "nv",
    "oy",
    "oyj",
    "ab",
    "as",
    "asa",
    "aps",
    "spa",
    "srl",
    "pty",
    "kk",
    "usa",
    "us",
    "america",
    "north",
    "the",
)

_PUNCT_RE = re.compile(r"[^0-9a-z]+")


def normalise_name(value: str) -> str:
    """NFC + casefold + whitespace collapse. The single normalisation used everywhere."""
    text = unicodedata.normalize("NFC", value or "")
    return " ".join(text.casefold().split())


def words(value: str) -> list[str]:
    return [token for token in _PUNCT_RE.split(normalise_name(value)) if token]


def lexical_key(value: str) -> str:
    """Normalised spelling with punctuation and trailing legal-form tokens removed.

    Only used to prove *equivalence* between two spellings of the same organization; it is
    never used as an attribution match, because dropping legal forms could merge different
    businesses.
    """
    tokens = words(value)
    while tokens and tokens[-1] in LEGAL_FORM_TOKENS:
        tokens.pop()
    # "co" / "kg" inside a name ("Draeger Medical AG & Co. KG") can appear mid-sequence; strip
    # the remaining legal tokens only from the tail so an inner token never changes meaning.
    changed = True
    while tokens and changed:
        changed = False
        while tokens and tokens[-1] in LEGAL_FORM_TOKENS:
            tokens.pop()
            changed = True
    return " ".join(tokens)


def contains_token_sequence(haystack: Sequence[str], needle: Sequence[str]) -> bool:
    if not needle or len(needle) > len(haystack):
        return False
    for start in range(len(haystack) - len(needle) + 1):
        if list(haystack[start:start + len(needle)]) == list(needle):
            return True
    return False


def contains_any_token(value: str, token: str) -> bool:
    return contains_token_sequence(words(value), words(token))


@dataclass(frozen=True)
class RuleResult:
    ok: bool
    rule: str | None
    detail: str


def name_identity_rule(applicant: str, *, legal_names: Iterable[str], brands: Iterable[str]) -> RuleResult:
    """Deterministic name-identity rule used for `rule_verified` (never for proposals)."""
    needle = normalise_name(applicant)
    if not needle:
        return RuleResult(False, None, "empty applicant name")
    for legal in legal_names:
        if legal and normalise_name(legal) == needle:
            return RuleResult(True, RULE_NAME_IDENTITY, "exact legal name")
    applicant_words = words(applicant)
    for brand in brands:
        brand_words = words(brand or "")
        if brand_words and contains_token_sequence(applicant_words, brand_words):
            return RuleResult(True, RULE_NAME_IDENTITY, "contains declared brand token sequence: " + " ".join(brand_words))
    return RuleResult(False, None, "no declared legal name or brand token sequence found")


# ---------------------------------------------------------------------------
# evidence records
# ---------------------------------------------------------------------------

EVIDENCE_TYPES = (
    "jurisdiction_filing",   # a filing exhibit or corporate registry document naming the entity
    "regulator_record",      # an official FDA/other regulator record naming the firm
    "corporate_document",    # annual report, list of subsidiaries, official company page
    "third_party_report",    # press/news/academic; weakest accepted documentary evidence
    "human_judgement",       # a named human states the decision without a document
    "agent_judgement",       # an AI agent states the decision without an independent document
)


@dataclass(frozen=True)
class EvidenceRef:
    evidence_type: str
    url: str | None = None
    title: str | None = None
    accessed_at: str | None = None
    source_id: str | None = None
    quote: str | None = None
    note: str | None = None

    def to_public(self) -> dict[str, Any]:
        return {
            "evidence_type": self.evidence_type,
            "url": self.url,
            "title": self.title,
            "accessed_at": self.accessed_at,
            "source_id": self.source_id,
            "quote": self.quote,
            "note": self.note,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "EvidenceRef":
        return cls(
            evidence_type=str(payload.get("evidence_type") or payload.get("type") or "corporate_document"),
            url=payload.get("url"),
            title=payload.get("title"),
            accessed_at=payload.get("accessed_at"),
            source_id=payload.get("source_id"),
            quote=payload.get("quote"),
            note=payload.get("note"),
        )


def evidence_justifies(evidence: Sequence[EvidenceRef]) -> bool:
    """True when at least one reference is independent documentary evidence.

    The kinds that justify `evidence_verified` are documents a third party produced; an agent's
    or a person's unsupported judgement is deliberately not enough. Those decisions stay
    `proposed`/`unresolved` (or `human_reviewed` when a named human takes responsibility).
    """
    documentary = {"jurisdiction_filing", "regulator_record", "corporate_document", "third_party_report"}
    return any(item.evidence_type in documentary and bool(item.url) for item in evidence)


def coerce_evidence(payload: Any) -> tuple[EvidenceRef, ...]:
    if not payload:
        return ()
    if isinstance(payload, Mapping):
        return (EvidenceRef.from_mapping(payload),)
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes)):
        out = []
        for item in payload:
            if isinstance(item, Mapping):
                out.append(EvidenceRef.from_mapping(item))
        return tuple(out)
    return ()


# ---------------------------------------------------------------------------
# summaries
# ---------------------------------------------------------------------------
def status_summary(counts: Mapping[str, int]) -> list[dict[str, Any]]:
    """Stable, ordered rows for API/UI/export: one row per status with label and meaning."""
    rows = []
    for status in DECISION_STATUSES:
        rows.append(
            {
                "status": status,
                "label_en": STATUS_LABELS_EN[status],
                "label_zh": STATUS_LABELS_ZH[status],
                "meaning_en": STATUS_MEANINGS_EN[status],
                "curated": is_curated(status),
                "rule_verified": is_rule_verified(status),
                "provisional": is_provisional(status),
                "count": int(counts.get(status, 0)),
            }
        )
    return rows


def metric_definitions() -> list[dict[str, Any]]:
    """The product's own definitions, shipped to the API, the UI and every export."""
    return [
        {
            "id": "attributed_share",
            "name_en": "Attributed Share",
            "name_zh": "已归属比例",
            "unit": "records",
            "definition_en": "Of the records in the collected sample, the share that carries any organization attribution. This measures the collection/attribution pipeline, not correctness.",
            "definition_zh": "在已采集样本中，被归属到某个跟踪企业的记录比例。它衡量采集与归属流程的覆盖程度，不代表归属正确。",
            "is_not": "NOT match precision, NOT match recall, NOT full-population FDA coverage.",
        },
        {
            "id": "rule_verified_share",
            "name_en": "Rule-verified Share",
            "name_zh": "规则校验比例",
            "unit": "records",
            "definition_en": "Of the attributed records, the share whose mapping is justified by a deterministic, reproducible name rule. A rule is not a reviewer.",
            "definition_zh": "在已归属记录中，所用身份映射可由确定性、可复现的名称规则解释的比例。规则校验不等于人工复核。",
            "is_not": "NOT independent evidence, NOT human review.",
        },
        {
            "id": "curated_share",
            "name_en": "Curated Share",
            "name_zh": "证据核验比例",
            "unit": "records",
            "definition_en": "Of the attributed records, the share whose mapping is evidence-verified (an independent documentary source is recorded) or human-reviewed. This is the only share the product counts as curated.",
            "definition_zh": "在已归属记录中，所用身份映射已通过独立证据核验或人工复核的比例。只有这一比例被计为已核验。",
            "is_not": "NOT the same as attributed share; it is typically far smaller.",
        },
        {
            "id": "estimated_attribution_precision",
            "name_en": "Estimated Attribution Precision",
            "name_zh": "归属准确率估计",
            "unit": "proportion with confidence interval",
            "definition_en": "The correctness of attributed mappings, estimated from a pre-registered independent sample review with a confidence interval. If no completed sample review exists the value is UNKNOWN.",
            "definition_zh": "通过预先固定的独立抽样复核估计的归属正确率，附置信区间。若无已完成的抽样复核，则报告 UNKNOWN。",
            "is_not": "NOT derivable from attributed share; an unknown value must be reported as unknown.",
        },
        {
            "id": "retrieval_coverage",
            "name_en": "Retrieval Coverage",
            "name_zh": "检索覆盖率",
            "unit": "proportion",
            "definition_en": "For a defined sampling frame, the share of the relevant population that the source queries retrieved. Without an independent truth denominator the value is UNKNOWN.",
            "definition_zh": "在明确抽样框下，来源查询找回相关记录的比例。若没有独立真值分母，则报告 UNKNOWN。",
            "is_not": "NOT the attributed share of the collected sample.",
        },
    ]
