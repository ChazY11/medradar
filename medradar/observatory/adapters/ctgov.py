"""ClinicalTrials.gov v2 adapter — observation of public trial registrations.

Why this source
---------------
A registration is a *public act by a sponsor* and, unlike a SEC accession, it is
not immutable: the registry keeps publishing structured metadata (overall
status, phase, enrollment, dates, conditions, interventions) that later changes
as the trial runs. That combination — a dated public statement that can be
revised — is exactly what the Live Observatory is for, and it is why a CT.gov
record can surface as ``UPDATED`` while an 8-K accession never does.

What "time" means here (the hard part)
--------------------------------------
ClinicalTrials.gov publishes **dates, not instants**. Three different source
dates are therefore stored separately and never substituted for one another:

* ``event_at``         = ``startDateStruct.date`` — when the study started.
* ``published_at``     = ``studyFirstPostDateStruct.date`` — when the
  registration first became publicly visible. This is the earliest public
  knowledge of the trial (the same rationale as ``medradar/clinical.py``); it is
  *not* the start date.
* ``source_updated_at`` = ``lastUpdatePostDateStruct.date`` — the registry's own
  last-publication date.

The precision stays ``date`` for a full date and ``year`` when the registry only
published ``YYYY-MM``; **no time of day is ever invented**, no timezone is
guessed, and nothing is rounded to "today". ``first_seen_at`` remains the
collector's own real wall clock and belongs to the ledger, not to this module.

Incremental collection
----------------------
Each scope is one sponsor-name query, sorted ``LastUpdatePostDate:desc`` and
paged with the API's own ``nextPageToken`` (so a run is truly resumable). A
per-scope watermark stores the newest ``lastUpdatePostDate`` seen plus the 25
most recent NCT ids; the next run only processes records with
``lastUpdatePostDate >= watermark - overlap`` and stops paging once a whole page
is older than that lower bound. Stopping is always reported in
``Page.note_zh`` (and in the run log) — never silently. A record whose metadata
changed remains detectable because the payload hash covers the source fields,
not the watermark window.

Honest coverage statement — read before quoting a count
-------------------------------------------------------
* The search term is the **curated roster name** (``config/companies_device.json``
  ``name_en`` or ``FEATURED_COMPANIES``) used verbatim. No spelling variants or
  subsidiary aliases are invented here.
* A sponsor search matches the *sponsor string the sponsor typed*. ``Medtronic
  Cardiac Rhythm and Heart Failure`` matches a ``Medtronic`` search, while
  ``Covidien`` (a Medtronic subsidiary) does **not**. Studies registered under a
  different sponsor string are therefore not observed, and the absence of an
  observation is **not** evidence that such a study does not exist.
* ``Dräger`` and ``Mindray`` are used exactly as curated (the diacritic spelling
  may not match every registry record); that limitation is reported, not fixed
  by inventing an alias.
* The first run looks back ``DEFAULT_INITIAL_DAYS`` of ``lastUpdatePostDate``
  instead of backfilling the registry: older registrations are deliberately not
  written into the live ledger (a historical ingestion has to be marked
  ``BACKFILLED`` by design). Within that window, a page-ceiling stop is also
  stated in the run log.
* Attribution (``map_record``) is derived from the study's **lead sponsor
  string** through the curated roster, never from the search term that found it:
  a study pulled in by a broad query but registered by an unrelated sponsor
  stays ``UNMAPPED`` rather than inheriting the query's company.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

from ...config import load_companies
from ...http import HttpError
from ...product.catalog import FEATURED_COMPANIES
from ...util import parse_date
from ..adapter import CollectContext
from ..mapping import ctgov_study
from ..records import (
    PRECISION_UNKNOWN,
    MappingResult,
    Page,
    RawRecord,
    Scope,
    normalize_moment,
)

SOURCE = "ctgov"
LABEL_ZH = "ClinicalTrials.gov 注册库"
COLLECTOR_VERSION = "ctgov/1.0.0"
RECORD_TYPE = "trial"
RECORD_TYPE_LABELS = {"trial": "临床试验注册"}
CADENCE_ZH = (
    "默认每 12 小时轮询；ClinicalTrials.gov 仅发布日期、不提供时间戳，"
    "因此观察时间精度为“天”；申办方名称检索无法覆盖名称不同的登记，不宣称完整"
)

API_URL = "https://clinicaltrials.gov/api/v2/studies"
STUDY_URL = "https://clinicaltrials.gov/study/{nct_id}"
#: Newest registry update first: makes the incremental lower bound and the
#: "stop when the page is entirely older than the watermark" rule meaningful.
SORT = "LastUpdatePostDate:desc"

#: Exactly the fields this adapter stores. Bounded on purpose (page size), and
#: verified against the live v2 API — an unknown field name is a hard 400 there.
FIELDS: tuple[str, ...] = (
    "NCTId",
    "BriefTitle",
    "OverallStatus",
    "Phase",
    "StudyType",
    "EnrollmentCount",
    "EnrollmentType",
    "LeadSponsorName",
    "CollaboratorName",
    "Condition",
    "InterventionType",
    "InterventionName",
    "InterventionOtherName",
    "InterventionDescription",
    "StartDate",
    "PrimaryCompletionDate",
    "CompletionDate",
    "StudyFirstPostDate",
    "LastUpdatePostDate",
    "HasResults",
)
FIELDS_PARAM = ",".join(FIELDS)

DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 100
#: First run: only look back this many days of ``lastUpdatePostDate``. The live
#: ledger does not backfill history (see the module docstring).
DEFAULT_INITIAL_DAYS = 90
#: Re-read a small window behind the watermark so same-day updates are caught.
DEFAULT_OVERLAP_DAYS = 3
#: Never chase a watermark older than this (a long pause must not page forever).
DEFAULT_MAX_CATCHUP_DAYS = 365
#: Safety valve on top of the engine's own page ceiling; hitting it is reported.
DEFAULT_MAX_PAGES = 40
KNOWN_ID_LIMIT = 25
#: The curated track taxonomy is a *device* taxonomy, so only device-type
#: interventions may feed the keyword matcher (a drug arm must not leak into a
#: device track just because the study happens to be filed by a device company).
DEVICE_INTERVENTION_TYPES = frozenset({"DEVICE", "DIAGNOSTIC_TEST"})

_TAG_RE = re.compile(r"<[^>]+>")
_HTTP_CURSOR_ERRORS = frozenset({400, 404})


# --------------------------------------------------------------------------- helpers
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _clean_text(value: Any) -> str:
    """Strip source markup and collapse whitespace for a *display* title only."""
    text = _TAG_RE.sub(" ", str(value or ""))
    return " ".join(text.split())


def _string_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        items = [str(item).strip() for item in value if str(item or "").strip()]
    elif value:
        items = [str(value).strip()]
    else:
        items = []
    result: list[str] = []
    for item in items:
        if item and item not in result:
            result.append(item)
    return result


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _struct_date(container: Any) -> str | None:
    value = container.get("date") if isinstance(container, Mapping) else None
    text = str(value or "").strip()
    return text or None


def _interventions(items: Any) -> tuple[list[dict[str, Any]], str | None]:
    """Normalise interventions; return them plus the device-intervention text."""
    parsed: list[dict[str, Any]] = []
    parts: list[str] = []
    for item in items or []:
        if not isinstance(item, Mapping):
            continue
        itype = str(item.get("type") or "").strip().upper() or None
        name = _clean_text(item.get("name")) or None
        other_names = _string_list(item.get("otherNames"))
        description = _clean_text(item.get("description")) or None
        parsed.append(
            {
                "type": itype,
                "name": name,
                "other_names": other_names,
                "description": description,
            }
        )
        if itype in DEVICE_INTERVENTION_TYPES:
            parts.extend(value for value in [name, description, *other_names] if value)
    return parsed, (" ".join(parts) or None)


def _decode_json(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    if isinstance(value, dict):
        return dict(value)
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


# --------------------------------------------------------------------------- adapter
class ClinicalTrialsAdapter:
    """One observation per NCT id, one scope per curated sponsor search term."""

    source_id = SOURCE
    label_zh = LABEL_ZH
    collector_version = COLLECTOR_VERSION
    declared_cadence_zh = CADENCE_ZH
    record_type_labels = RECORD_TYPE_LABELS

    def __init__(
        self,
        *,
        companies: list[str] | None = None,
        all_companies: bool = False,
        max_companies: int | None = None,
        page_size: int = DEFAULT_PAGE_SIZE,
        initial_days: int = DEFAULT_INITIAL_DAYS,
        overlap_days: int = DEFAULT_OVERLAP_DAYS,
        max_catchup_days: int = DEFAULT_MAX_CATCHUP_DAYS,
        max_pages: int = DEFAULT_MAX_PAGES,
    ) -> None:
        self.company_filter = [str(key).strip() for key in (companies or []) if str(key).strip()]
        self.all_companies = bool(all_companies)
        self.max_companies = max_companies
        self.page_size = max(1, min(int(page_size), MAX_PAGE_SIZE))
        self.initial_days = max(1, int(initial_days))
        self.overlap_days = max(0, int(overlap_days))
        self.max_catchup_days = max(1, int(max_catchup_days))
        self.max_pages = max(0, int(max_pages))
        self._session_run: str | None = None
        self._watermarks: dict[str, Any] = {}
        self._known: dict[str, list[str]] = {}
        self._scope_max: dict[str, date] = {}
        self._pages: dict[str, int] = {}
        self._windows: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------ planning
    def _reset_session(self, ctx: CollectContext) -> None:
        """Reload per-scope watermarks once per run (never per page)."""
        if self._session_run == ctx.run_id:
            return
        self._session_run = ctx.run_id
        state = ctx.ledger.get_source_state(SOURCE) or {}
        self._watermarks = _decode_json(state.get("watermark"))
        self._known = {}
        self._scope_max = {}
        self._pages = {}
        self._windows = {}

    def _candidates(self) -> list[dict[str, Any]]:
        """Curated sponsor search terms — the featured five, optionally the roster.

        The term is the curated ``name_en`` verbatim: this adapter does not
        derive, translate or invent aliases (see the module docstring).
        """
        roster = {str(company["key"]): company for company in load_companies("device").all()}
        chosen: dict[str, dict[str, Any]] = {}
        for featured in FEATURED_COMPANIES:
            key = str(featured["key"])
            base = roster.get(key) or {}
            base_name = str(base.get("name_en") or "").strip()
            featured_name = str(featured.get("name_en") or "").strip()
            term = base_name or featured_name
            if not term:
                continue
            chosen[key] = {
                "key": key,
                "term": term,
                "term_source": (
                    "config/companies_device.json:name_en"
                    if base_name
                    else "medradar/product/catalog.py:FEATURED_COMPANIES.name_en"
                ),
                "in_roster": key in roster,
            }
        if self.all_companies:
            for key, company in roster.items():
                if key in chosen:
                    continue
                term = str(company.get("name_en") or "").strip()
                if not term:
                    continue
                chosen[key] = {
                    "key": key,
                    "term": term,
                    "term_source": "config/companies_device.json:name_en",
                    "in_roster": True,
                }
        if self.company_filter:
            keep = set(self.company_filter)
            unknown = keep - set(chosen)
            if unknown:
                raise ValueError(
                    "unknown company key(s) for ClinicalTrials.gov coverage: "
                    + ", ".join(sorted(unknown))
                )
            chosen = {key: value for key, value in chosen.items() if key in keep}
        items = list(chosen.values())
        if self.max_companies:
            items = items[: int(self.max_companies)]
        return items

    def plan(self, ctx: CollectContext) -> list[Scope]:
        self._reset_session(ctx)
        scopes: list[Scope] = []
        for candidate in self._candidates():
            scopes.append(
                Scope(
                    scope_id=f"spons:{candidate['key']}:{candidate['term']}",
                    params={
                        "company_key": candidate["key"],
                        "sponsor": candidate["term"],
                        "term_source": candidate["term_source"],
                    },
                )
            )
        return scopes

    # ----------------------------------------------------------------- fetching
    def _watermark(self, scope: Scope) -> dict[str, Any]:
        value = self._watermarks.get(scope.scope_id)
        return value if isinstance(value, dict) else {}

    def _window(self, scope: Scope, now: datetime) -> dict[str, Any]:
        """Inclusive ``lastUpdatePostDate`` lower bound for this run."""
        today = now.date()
        floor = today - timedelta(days=self.max_catchup_days)
        notes: list[str] = []
        latest = parse_date(self._watermark(scope).get("last_update_post_date"))
        if latest is not None:
            lower = latest - timedelta(days=self.overlap_days)
            if lower < floor:
                lower = floor
                notes.append(
                    f"增量下界早于最多回溯 {self.max_catchup_days} 天，已截断为 {lower.isoformat()}（更早的更新不再追溯）"
                )
        else:
            lower = max(floor, today - timedelta(days=self.initial_days))
            notes.append(
                f"首次运行（无水位）：只观察最近 {self.initial_days} 天有更新的登记，不回填更早历史"
            )
        return {"lower": lower, "notes": notes}

    def _window_for(self, scope: Scope, now: datetime) -> dict[str, Any]:
        """The lower bound is fixed for the whole scope *within one run*.

        It must not follow the watermark as pages advance: otherwise the second
        page of a fast-moving scope would be compared with a later bound than
        the first page and records between the two bounds would be skipped.
        """
        cached = self._windows.get(scope.scope_id)
        if cached is None:
            cached = self._window(scope, now)
            self._windows[scope.scope_id] = cached
        return cached

    def fetch_page(self, ctx: CollectContext, scope: Scope, cursor: str | None) -> Page:
        self._reset_session(ctx)
        sponsor = str(scope.params.get("sponsor") or "").strip()
        if not sponsor:
            raise ValueError(f"scope {scope.scope_id!r} has no sponsor search term")
        now = _parse_iso(ctx.now) or _utcnow()
        window = self._window_for(scope, now)
        lower: date = window["lower"]
        notes: list[str] = list(window["notes"])

        params: dict[str, Any] = {
            "query.spons": sponsor,
            "pageSize": self.page_size,
            "sort": SORT,
            "fields": FIELDS_PARAM,
        }
        if cursor:
            params["pageToken"] = cursor
        try:
            payload = ctx.get_json(API_URL, params)
        except HttpError as exc:
            # A checkpointed page token can expire between runs. Restarting the
            # scope from page 1 re-reads pages already in the ledger (they come
            # back UNCHANGED) instead of wedging the scope forever.
            if cursor and int(getattr(exc, "status", 0) or 0) in _HTTP_CURSOR_ERRORS:
                notes.append(f"检查点游标失效（{exc}），本次从第一页重新开始；已观察记录不会丢失")
                ctx.log(f"[{SOURCE}] cursor {cursor[:24]!r} rejected; restarting scope {scope.scope_id} from page 1")
                ctx.ledger.record_failure(
                    SOURCE,
                    kind="HTTP_ERROR",
                    message=f"checkpoint page token rejected; restarted scope {scope.scope_id} from page 1: {exc}",
                    run_id=ctx.run_id,
                    url=API_URL,
                    http_status=int(getattr(exc, "status", 0) or 0),
                    retryable=False,
                )
                params.pop("pageToken", None)
                payload = ctx.get_json(API_URL, params)
            else:
                raise
        if not isinstance(payload, Mapping):
            raise ValueError(
                f"ClinicalTrials.gov returned {type(payload).__name__}, expected a JSON object"
            )
        raw_studies = payload.get("studies")
        if raw_studies is None:
            raw_studies = []
        if not isinstance(raw_studies, list):
            raise ValueError("ClinicalTrials.gov field 'studies' is not a list")

        records: list[RawRecord] = []
        skipped_old = 0
        undated = 0
        unidentifiable = 0
        page_max: date | None = None
        all_dated_older = bool(raw_studies)
        for study in raw_studies:
            if not isinstance(study, Mapping):
                raise ValueError("ClinicalTrials.gov returned a non-object study entry")
            updated = _study_updated(study)
            if updated is None:
                undated += 1
                all_dated_older = False
            else:
                if page_max is None or updated > page_max:
                    page_max = updated
                if updated < lower:
                    skipped_old += 1
                    continue
                all_dated_older = False
            record = self._to_record(study, scope)
            if record is None:
                unidentifiable += 1
                continue
            records.append(record)

        if undated:
            all_dated_older = False
        next_cursor: str | None = None
        token = payload.get("nextPageToken")
        if token:
            next_cursor = str(token)
        if all_dated_older and skipped_old:
            # Newest-first order: if this whole page is behind the lower bound,
            # every following page is too. Say what was *not* read.
            next_cursor = None
            notes.append(
                f"本页 {skipped_old} 条登记的 lastUpdatePostDate 全部早于增量下界 {lower.isoformat()}，"
                "按增量停止翻页；更旧的登记本次未取（不是完整历史，也未被视为“无变化”）"
            )
            ctx.log(
                f"[{SOURCE}] scope {scope.scope_id}: stopped paging at incremental lower bound "
                f"{lower.isoformat()} (whole page older)"
            )
        elif next_cursor and self.max_pages and self._pages_of(scope) >= self.max_pages:
            next_cursor = None
            notes.append(
                f"已达单次运行页数上限 {self.max_pages} 页，范围 {scope.scope_id} 尚未取尽；"
                "剩余记录未观察（可继续运行，但本次不宣称完整）"
            )
            ctx.log(
                f"[{SOURCE}] scope {scope.scope_id}: page ceiling {self.max_pages} reached; "
                "the window is NOT fully observed"
            )

        if skipped_old and not all_dated_older:
            notes.append(
                f"{skipped_old} 条登记的 lastUpdatePostDate 早于增量下界 {lower.isoformat()}，"
                "本次未处理（增量跳过，不代表删除）"
            )
        if undated:
            notes.append(f"{undated} 条登记缺少 lastUpdatePostDate，已照常观察（无法放入增量窗口）")
        if unidentifiable:
            notes.append(f"{unidentifiable} 条登记缺少 NCTId，无法建立稳定标识，未写入账本（不伪造标识）")

        self._pages[scope.scope_id] = self._pages.get(scope.scope_id, 0) + 1
        watermark = self._build_watermark(scope, sponsor, page_max, records)
        return Page(
            records=records,
            next_cursor=next_cursor,
            watermark=watermark,
            structure_sample=self._structure_sample(payload, raw_studies),
            note_zh="；".join(notes) if notes else None,
        )

    def _pages_of(self, scope: Scope) -> int:
        """Pages fetched for this scope *including* the page being built."""
        return int(self._pages.get(scope.scope_id, 0)) + 1

    def _build_watermark(
        self, scope: Scope, sponsor: str, page_max: date | None, records: Sequence[RawRecord]
    ) -> dict[str, Any]:
        """Never regress: keep the newest ``lastUpdatePostDate`` this scope saw."""
        prior = self._watermark(scope)
        prior_max = parse_date(prior.get("last_update_post_date"))
        running_max = self._scope_max.get(scope.scope_id)
        candidates = [value for value in (prior_max, running_max, page_max) if value is not None]
        high = max(candidates) if candidates else None
        if high is not None:
            self._scope_max[scope.scope_id] = high
        known = self._known.setdefault(scope.scope_id, [])
        for record in records:
            if record.source_record_id not in known:
                known.append(record.source_record_id)
        watermark = {
            "last_update_post_date": high.isoformat() if high else None,
            "known_ids": known[:KNOWN_ID_LIMIT],
            "company_key": scope.params.get("company_key"),
            "sponsor": sponsor,
        }
        self._watermarks[scope.scope_id] = watermark
        return watermark

    @staticmethod
    def _structure_sample(payload: Mapping[str, Any], studies: Sequence[Any]) -> dict[str, Any]:
        """Fingerprint the *API envelope*, not one study's optional fields.

        An individual registration legitimately omits optional modules (design for
        some observational studies, conditions for device studies, interventions
        for records without an arm). Hashing one study's key set therefore raises
        false "structure changed" alarms on ordinary data. What must stay stable is
        the envelope plus the always-present protocol modules the parser depends
        on; a real v2 contract change still moves this signature.
        """
        sample_study = studies[0] if studies and isinstance(studies[0], Mapping) else {}
        protocol = sample_study.get("protocolSection") or {}
        protocol = protocol if isinstance(protocol, Mapping) else {}
        identification = protocol.get("identificationModule")
        status = protocol.get("statusModule")
        return {
            "response_has_studies": "studies" in payload,
            "study_has_protocol": bool(protocol),
            "study_has_protocol_module": isinstance(sample_study.get("protocolSection"), Mapping),
            "required_protocol_modules": {
                name: isinstance(protocol.get(name), Mapping)
                for name in ("identificationModule", "statusModule",
                             "sponsorCollaboratorsModule")
            },
            "identification_has_nctid": isinstance(identification, Mapping)
            and ("nctId" in identification),
            "status_has_overall_status": isinstance(status, Mapping)
            and ("overallStatus" in status),
            "status_has_first_post_date": isinstance(status, Mapping)
            and ("studyFirstPostDateStruct" in status),
        }

    # ------------------------------------------------------------------- mapping
    def _to_record(self, study: Mapping[str, Any], scope: Scope) -> RawRecord | None:
        protocol = study.get("protocolSection") or {}
        if not isinstance(protocol, Mapping):
            raise ValueError("ClinicalTrials.gov study 'protocolSection' is not an object")
        identification = protocol.get("identificationModule") or {}
        nct_id = str(identification.get("nctId") or "").strip()
        if not nct_id:
            return None
        status_module = protocol.get("statusModule") or {}
        design = protocol.get("designModule") or {}
        sponsor_module = protocol.get("sponsorCollaboratorsModule") or {}
        conditions_module = protocol.get("conditionsModule") or {}
        interventions_module = protocol.get("armsInterventionsModule") or {}

        start_raw = _struct_date(status_module.get("startDateStruct"))
        first_post_raw = _struct_date(status_module.get("studyFirstPostDateStruct"))
        last_update_raw = _struct_date(status_module.get("lastUpdatePostDateStruct"))
        primary_completion_raw = _struct_date(status_module.get("primaryCompletionDateStruct"))
        completion_raw = _struct_date(status_module.get("completionDateStruct"))

        lead_sponsor = str((sponsor_module.get("leadSponsor") or {}).get("name") or "").strip()
        collaborators = [
            str((item or {}).get("name") or "").strip()
            for item in (sponsor_module.get("collaborators") or [])
            if isinstance(item, Mapping)
        ]
        collaborators = [name for name in collaborators if name]
        conditions = _string_list(conditions_module.get("conditions"))
        interventions, intervention_text = _interventions(interventions_module.get("interventions"))
        phases = _string_list(design.get("phases"))
        enrollment_info = design.get("enrollmentInfo") or {}
        enrollment_count = _int_or_none(enrollment_info.get("count"))
        enrollment_type = str(enrollment_info.get("type") or "").strip() or None
        study_type = str(design.get("studyType") or "").strip() or None
        overall_status = str(status_module.get("overallStatus") or "").strip() or None
        brief_title_raw = str(identification.get("briefTitle") or "").strip()
        has_results_value = study.get("hasResults")
        has_results = bool(has_results_value) if has_results_value is not None else None

        event_at, event_precision = (
            normalize_moment(start_raw) if start_raw else (None, PRECISION_UNKNOWN)
        )
        published_at, published_precision = (
            normalize_moment(first_post_raw) if first_post_raw else (None, PRECISION_UNKNOWN)
        )
        source_updated_at, source_updated_precision = (
            normalize_moment(last_update_raw) if last_update_raw else (None, PRECISION_UNKNOWN)
        )

        payload: dict[str, Any] = {
            "nct_id": nct_id,
            "brief_title": brief_title_raw or None,
            "overall_status": overall_status,
            "phases": phases,
            "study_type": study_type,
            "enrollment_count": enrollment_count,
            "enrollment_type": enrollment_type,
            "lead_sponsor": lead_sponsor or None,
            "collaborators": collaborators,
            "conditions": conditions,
            "interventions": interventions,
            "start_date": start_raw,
            "primary_completion_date": primary_completion_raw,
            "completion_date": completion_raw,
            "study_first_post_date": first_post_raw,
            "last_update_post_date": last_update_raw,
            "has_results": has_results,
        }
        display_title = f"{_clean_text(brief_title_raw) or nct_id}｜{nct_id}"
        return RawRecord(
            source=SOURCE,
            source_record_id=nct_id,
            record_type=RECORD_TYPE,
            title=display_title,
            url=STUDY_URL.format(nct_id=nct_id),
            event_at=event_at,
            event_at_precision=event_precision,
            published_at=published_at,
            published_at_precision=published_precision,
            source_updated_at=source_updated_at,
            source_updated_at_precision=source_updated_precision,
            payload=payload,
            company_hint=lead_sponsor or None,
            extra={
                "nct_id": nct_id,
                "company_key": scope.params.get("company_key"),
                "sponsor_query": scope.params.get("sponsor"),
                "lead_sponsor": lead_sponsor or None,
                "device_intervention_text": intervention_text,
            },
        )

    def map_record(self, record: RawRecord, ctx: CollectContext) -> MappingResult:
        """Attribution from the *study's lead sponsor*, not from the query term."""
        extra = record.extra or {}
        sponsor = str(extra.get("lead_sponsor") or record.company_hint or "").strip() or None
        intervention_text = extra.get("device_intervention_text")
        return ctgov_study(sponsor, str(intervention_text) if intervention_text else None)

    # ------------------------------------------------------------- failure scope
    def scope_known_ids(self, ctx: CollectContext, scope: Scope) -> list[str]:
        """Observation ids already known for this scope (for ``FETCH_FAILED``)."""
        known: list[str] = []
        for item in self._watermark(scope).get("known_ids") or []:
            text = str(item).strip()
            if text and text not in known:
                known.append(text)
        for item in list(self._known.get(scope.scope_id, [])):
            if item and item not in known:
                known.append(item)
        if not known:
            return []
        ids = ctx.ledger.observation_ids_for(SOURCE, known[:KNOWN_ID_LIMIT])
        return list(ids.values())[:KNOWN_ID_LIMIT]


def _study_updated(study: Mapping[str, Any]) -> date | None:
    protocol = study.get("protocolSection") or {}
    if not isinstance(protocol, Mapping):
        return None
    raw = _struct_date((protocol.get("statusModule") or {}).get("lastUpdatePostDateStruct"))
    return parse_date(raw) if raw else None


__all__ = [
    "ClinicalTrialsAdapter",
    "API_URL",
    "FIELDS",
    "FIELDS_PARAM",
    "SORT",
    "SOURCE",
    "LABEL_ZH",
]
