"""An isolated fixture source, used only by the acceptance runs.

This adapter exists so that the *change-detection* path can be exercised against a source whose
bytes this system controls: a directory of JSON pages on local disk. It is deliberately **not**
registered in :data:`medradar.radar.adapters.FACTORIES`, so it can never appear in a production
source list, and the product UI never sees it.

It is a test harness for the mechanism, not synthetic news: every record it returns is clearly a
fixture (``record_type`` is still a real type, but the source id and the payload say so), and the
acceptance report labels the run as a controlled change test rather than live discovery.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..adapter import CollectContext
from ..http import FetchError
from ..records import MappingResult, Page, RawRecord, Scope, normalize_moment


class FixtureAdapter:
    """Read ``<root>/page-<n>.json`` files as a paginated, mutable source."""

    source_id = "fixture_isolated"
    label = "Isolated fixture source (acceptance only)"
    adapter_version = "radar-fixture-1"
    declared_cadence_hours = 1.0
    record_types = ("publication",)
    enabled = True
    access_state = "ENABLED"
    access_reason = None

    def __init__(self, taxonomy, root: str | Path, *, fail_on_page: int | None = None) -> None:
        self.taxonomy = taxonomy
        self.root = Path(root)
        self.fail_on_page = fail_on_page

    def plan(self, ctx: CollectContext) -> list[Scope]:
        return [Scope("pages")]

    def fetch_page(self, ctx: CollectContext, scope: Scope, cursor: str | None) -> Page:
        index = int(cursor or 0)
        if not self.root.is_dir():
            raise FetchError(f"fixture root {self.root} does not exist (source unavailable)",
                             url=f"fixture://{self.root}")
        if self.fail_on_page is not None and index == self.fail_on_page:
            raise FetchError(f"simulated transport failure on page {index}",
                             url=f"fixture://page-{index}")
        path = self.root / f"page-{index}.json"
        if not path.is_file():
            return Page(records=[], next_cursor=None, watermark=ctx.watermark,
                        note="no further fixture pages")
        payload = json.loads(path.read_text(encoding="utf-8"))
        records = [_record(row) for row in payload.get("records") or []]
        next_cursor = str(index + 1) if (self.root / f"page-{index + 1}.json").is_file() else None
        return Page(records=records, next_cursor=next_cursor,
                    watermark=payload.get("watermark"),
                    removed_ids=list(payload.get("removed_ids") or []))

    def map_record(self, record: RawRecord, ctx: CollectContext) -> MappingResult:
        from ..classify import RuleMapper

        return RuleMapper(self.taxonomy).map(record)


def _record(row: dict[str, Any]) -> RawRecord:
    published, precision = normalize_moment(row.get("published_at"))
    return RawRecord(
        source="fixture_isolated",
        source_record_id=str(row["id"]),
        official_identifier=str(row.get("official_identifier") or row["id"]),
        record_type=str(row.get("record_type") or "publication"),
        title=str(row["title"]),
        url=row.get("url"),
        published_at=published,
        published_at_precision=precision,
        event_at=published,
        event_at_precision=precision,
        payload=dict(row.get("payload") or {"title": row["title"]}),
        text=" ".join(filter(None, [str(row["title"]), str(row.get("text") or "")])),
        extra=dict(row.get("extra") or {}),
    )


def write_pages(root: str | Path, pages: list[dict[str, Any]]) -> None:
    """Helper for the acceptance script: (re)write the fixture pages."""
    path = Path(root)
    path.mkdir(parents=True, exist_ok=True)
    for index, page in enumerate(pages):
        (path / f"page-{index}.json").write_text(
            json.dumps(page, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    for stale in path.glob("page-*.json"):
        number = int(stale.stem.split("-", 1)[1])
        if number >= len(pages):
            stale.unlink()
