"""Entity roster and taxonomy, loaded from ``config/`` -- deterministic only.

Two closed vocabularies make a model output scorable:

* :class:`EntityRoster` -- the canonical company ids and their aliases.  The
  roster is *configuration*, not code: it comes from
  ``config/universe_v1.json`` ``focus_companies`` (the five deep-case firms) and
  from ``config/companies_device.json``.  No canonical id is written into this
  module, so swapping the universe cannot silently leave a stub behind.
* :class:`Taxonomy` -- the technology domains and their finer track ids from
  ``config/tracks_device.json`` (plus any track name that
  ``config/product_code_tracks.json`` might add).  It answers the only question
  the validator asks: is this ``technology_domains`` entry a declared term?

Matching policy
---------------
Alias matching is exact modulo **NFC + casefold**, with word boundaries, and
"longest alias wins" for tie-breaking.  There is no stemming, no token
containment score, no similarity threshold: a substring match with a confidence
floor is exactly the kind of fuzzy join that makes an entity metric
unreproducible.  If a document names a company under an alias that is not in the
roster, the validator reports ``ENTITY_ALIAS_NOT_IN_DOCUMENT`` /
``ENTITY_NOT_IN_ROSTER`` instead of guessing.

The constructors
----------------
``from_config()`` is the real wiring; ``from_synthetic()`` exists so tests never
need a config file and so a benchmark can build a controlled roster.  Both
return the same class.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

__all__ = [
    "EntityRecord",
    "EntityRoster",
    "DomainRecord",
    "TrackRecord",
    "Taxonomy",
    "default_config_dir",
    "fold",
]


# ------------------------------------------------------------------- base paths
def default_config_dir() -> Path:
    """Resolve the repository ``config/`` directory without hard-coding a path.

    Resolution order: ``MEDRADAR_CONFIG_DIR`` (the product's existing override),
    then the ``config/`` directory of the checkout this file lives in.
    """
    override = os.environ.get("MEDRADAR_CONFIG_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[3] / "config"


def _resolve_config_dir(config_dir: str | os.PathLike[str] | None) -> Path:
    return Path(config_dir) if config_dir is not None else default_config_dir()


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def fold(text: str) -> str:
    """NFC + casefold: the *whole* normalisation the matchers are allowed."""
    return unicodedata.normalize("NFC", text).casefold()


def _clean_aliases(raw: Any) -> tuple[str, ...]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return ()
    seen: dict[str, None] = {}
    for item in raw:
        if not isinstance(item, str):
            continue
        alias = item.strip()
        if alias:
            seen.setdefault(alias, None)
    return tuple(seen)


_ALIAS_BOUNDARY_CACHE: dict[str, re.Pattern[str]] = {}


def _alias_pattern(alias: str) -> re.Pattern[str]:
    """Word-boundary pattern for one folded alias (deterministic substring)."""
    cached = _ALIAS_BOUNDARY_CACHE.get(alias)
    if cached is None:
        cached = re.compile(r"(?<!\w)" + re.escape(alias) + r"(?!\w)")
        _ALIAS_BOUNDARY_CACHE[alias] = cached
    return cached


# ---------------------------------------------------------------- entity roster
@dataclass(frozen=True)
class EntityRecord:
    """One canonical company and the aliases that resolve to it."""

    canonical_id: str
    display_name: str
    aliases: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_id": self.canonical_id,
            "display_name": self.display_name,
            "aliases": list(self.aliases),
            "sources": list(self.sources),
        }


class EntityRoster:
    """Canonical company ids plus their deterministic alias index."""

    def __init__(self, records: Iterable[EntityRecord]) -> None:
        by_id: dict[str, EntityRecord] = {}
        for record in records:
            if not isinstance(record, EntityRecord):
                raise TypeError("EntityRoster expects EntityRecord instances")
            if not record.canonical_id:
                raise ValueError("canonical_id must be a non-empty string")
            existing = by_id.get(record.canonical_id)
            if existing is None:
                by_id[record.canonical_id] = record
                continue
            merged_aliases = tuple(
                dict.fromkeys((*existing.aliases, *record.aliases))
            )
            merged_sources = tuple(dict.fromkeys((*existing.sources, *record.sources)))
            by_id[record.canonical_id] = EntityRecord(
                canonical_id=record.canonical_id,
                display_name=existing.display_name or record.display_name,
                aliases=merged_aliases,
                sources=merged_sources,
            )
        if not by_id:
            raise ValueError("an entity roster needs at least one record")
        self._records = by_id
        # Longest alias first; ties broken by canonical id then alias for
        # deterministic resolution.
        index: list[tuple[str, str, str]] = []
        for canonical_id, record in by_id.items():
            for alias in record.aliases:
                folded = fold(alias)
                if folded:
                    index.append((folded, canonical_id, alias))
        index.sort(key=lambda item: (-len(item[0]), item[0], item[1], item[2]))
        self._alias_index = tuple(index)

    # -- construction --------------------------------------------------------
    @classmethod
    def from_synthetic(
        cls,
        companies: Mapping[str, Sequence[str] | Mapping[str, Any]]
        | Sequence[Mapping[str, Any] | tuple[str, Any] | str]
        | str
        | None = None,
        **canonical_aliases: Any,
    ) -> "EntityRoster":
        """Build a roster from plain data, e.g. ``{"acme": ["ACME"]}``.

        Accepted shapes::

            EntityRoster.from_synthetic({"acme": ["ACME", "ACME CORP"]})
            EntityRoster.from_synthetic([{"canonical_id": "x", "aliases": [...]}])
            EntityRoster.from_synthetic([("x", ["ALIAS"])])
            EntityRoster.from_synthetic(["x", "y"])
            EntityRoster.from_synthetic(acme=["ACME"])
        """
        records: list[EntityRecord] = []

        def add(canonical_id: str, payload: Any) -> None:
            if not canonical_id:
                raise ValueError("synthetic company entries need a canonical id")
            if payload is None:
                aliases: tuple[str, ...] = ()
                display_name = canonical_id
                sources: tuple[str, ...] = ()
            elif isinstance(payload, str):
                aliases = _clean_aliases([payload])
                display_name = canonical_id
                sources = ()
            elif isinstance(payload, Mapping):
                aliases = _clean_aliases(payload.get("aliases", ()))
                display_name = str(
                    payload.get("display_name") or payload.get("name") or canonical_id
                )
                sources = tuple(str(source) for source in payload.get("sources", ()))
            elif isinstance(payload, Sequence):
                aliases = _clean_aliases(payload)
                display_name = canonical_id
                sources = ()
            else:
                raise TypeError(f"unsupported synthetic company payload {payload!r}")
            records.append(
                EntityRecord(
                    canonical_id=canonical_id,
                    display_name=display_name,
                    aliases=aliases,
                    sources=sources or ("synthetic",),
                )
            )

        if companies is not None:
            if isinstance(companies, Mapping):
                for canonical_id, payload in companies.items():
                    add(str(canonical_id), payload)
            elif isinstance(companies, str):
                add(companies, None)
            elif isinstance(companies, Sequence):
                for entry in companies:
                    if isinstance(entry, Mapping):
                        canonical_id = str(
                            entry.get("canonical_id")
                            or entry.get("key")
                            or entry.get("id")
                            or ""
                        )
                        add(canonical_id, entry)
                    elif isinstance(entry, (tuple, list)) and len(entry) == 2:
                        add(str(entry[0]), entry[1])
                    elif isinstance(entry, str):
                        add(entry, None)
                    else:
                        raise TypeError(f"unsupported synthetic company entry {entry!r}")
            else:
                raise TypeError(f"unsupported synthetic roster payload {companies!r}")
        for canonical_id, payload in canonical_aliases.items():
            add(str(canonical_id), payload)
        if not records:
            raise ValueError("an entity roster needs at least one company")
        return cls(records)

    @classmethod
    def from_config(
        cls,
        config_dir: str | os.PathLike[str] | None = None,
        *,
        include_device_companies: bool = True,
    ) -> "EntityRoster":
        """Load the five-firm roster and the curated device company list.

        Raises ``FileNotFoundError`` when the configuration is absent: a roster
        built from nothing would validate every company as unknown, so failing
        loudly is the honest behaviour.
        """
        directory = _resolve_config_dir(config_dir)
        collected: dict[str, dict[str, Any]] = {}

        def _add(canonical_id: str, display_name: str | None, aliases: Any, source: str) -> None:
            if not canonical_id:
                return
            entry = collected.setdefault(
                canonical_id,
                {"display_name": display_name or canonical_id, "aliases": [], "sources": []},
            )
            entry["aliases"].extend(_clean_aliases(aliases))
            if display_name:
                entry["display_name"] = display_name
            if source not in entry["sources"]:
                entry["sources"].append(source)

        universe_path = directory / "universe_v1.json"
        if universe_path.exists():
            universe = _read_json(universe_path)
            focus = universe.get("focus_companies") if isinstance(universe, Mapping) else None
            if isinstance(focus, Mapping):
                for canonical_id, payload in focus.items():
                    if not isinstance(payload, Mapping):
                        continue
                    _add(
                        str(canonical_id),
                        payload.get("display_name"),
                        payload.get("aliases", ()),
                        "universe_v1.json:focus_companies",
                    )

        if include_device_companies:
            device_path = directory / "companies_device.json"
            if device_path.exists():
                device = _read_json(device_path)
                companies = device.get("companies") if isinstance(device, Mapping) else None
                if isinstance(companies, Sequence) and not isinstance(companies, (str, bytes)):
                    for company in companies:
                        if not isinstance(company, Mapping):
                            continue
                        _add(
                            str(company.get("key") or ""),
                            company.get("name_en"),
                            company.get("aliases", ()),
                            "companies_device.json",
                        )

        if not collected:
            raise FileNotFoundError(
                f"no entity configuration found under {str(directory)!r}: expected "
                "universe_v1.json and/or companies_device.json"
            )
        return cls(
            EntityRecord(
                canonical_id=canonical_id,
                display_name=payload["display_name"],
                aliases=tuple(payload["aliases"]),
                sources=tuple(payload["sources"]),
            )
            for canonical_id, payload in collected.items()
        )

    # -- queries -------------------------------------------------------------
    @property
    def canonical_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._records))

    @property
    def records(self) -> tuple[EntityRecord, ...]:
        """All records, sorted by canonical id (deterministic order)."""
        return tuple(self._records[key] for key in self.canonical_ids)

    def __len__(self) -> int:
        return len(self._records)

    def __contains__(self, canonical_id: object) -> bool:
        return canonical_id in self._records

    def record(self, canonical_id: str) -> EntityRecord | None:
        return self._records.get(canonical_id)

    def display_name(self, canonical_id: str) -> str | None:
        record = self._records.get(canonical_id)
        return record.display_name if record else None

    def aliases_for(self, canonical_id: str) -> tuple[str, ...]:
        record = self._records.get(canonical_id)
        return record.aliases if record else ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_ids": list(self.canonical_ids),
            "records": [self._records[key].to_dict() for key in self.canonical_ids],
        }

    def alias_in_text(self, alias: str, text: str) -> bool:
        """True when ``alias`` occurs in ``text`` under NFC+casefold+word boundaries."""
        if not alias or not text:
            return False
        return _alias_pattern(fold(alias)).search(fold(text)) is not None

    def resolve_alias(self, text: str) -> str | None:
        """Resolve free text to a canonical id: longest matching alias wins."""
        if not text:
            return None
        folded = fold(text)
        for folded_alias, canonical_id, _raw_alias in self._alias_index:
            if _alias_pattern(folded_alias).search(folded):
                return canonical_id
        return None

    def canonical_ids_in_text(self, text: str) -> tuple[str, ...]:
        """Every canonical id whose alias appears in ``text`` (sorted, unique)."""
        if not text:
            return ()
        folded = fold(text)
        found: set[str] = set()
        for folded_alias, canonical_id, _raw_alias in self._alias_index:
            if canonical_id in found:
                continue
            if _alias_pattern(folded_alias).search(folded):
                found.add(canonical_id)
        return tuple(sorted(found))

    def canonical_id_named_in_document(
        self,
        canonical_id: str,
        document_text: str,
        *,
        raw_text: str | None = None,
    ) -> bool:
        """True when the document names the company, via its alias or the claim.

        ``raw_text`` is the text the extractor says it saw; when supplied, a
        verbatim appearance of it also proves the document named the company.
        """
        if raw_text and self.alias_in_text(raw_text, document_text):
            return True
        return any(self.alias_in_text(alias, document_text) for alias in self.aliases_for(canonical_id))


# --------------------------------------------------------------------- taxonomy
@dataclass(frozen=True)
class DomainRecord:
    """One declared technology domain."""

    domain_id: str
    name_en: str | None = None
    name_zh: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"domain_id": self.domain_id, "name_en": self.name_en, "name_zh": self.name_zh}


@dataclass(frozen=True)
class TrackRecord:
    """One declared technology track (finer-grained than a domain)."""

    track_id: str
    name_en: str | None = None
    name_zh: str | None = None
    domain: str | None = None
    category: str | None = None
    sources: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "track_id": self.track_id,
            "name_en": self.name_en,
            "name_zh": self.name_zh,
            "domain": self.domain,
            "category": self.category,
            "sources": list(self.sources),
        }


class Taxonomy:
    """Declared technology domains and tracks, loaded from configuration."""

    def __init__(
        self,
        tracks: Iterable[TrackRecord] = (),
        domains: Iterable[DomainRecord] = (),
    ) -> None:
        self._tracks: dict[str, TrackRecord] = {}
        for track in tracks:
            if not isinstance(track, TrackRecord):
                raise TypeError("Taxonomy expects TrackRecord instances")
            if not track.track_id:
                raise ValueError("track_id must be a non-empty string")
            if track.track_id in self._tracks:
                # Merge rather than silently keep whichever came last.
                existing = self._tracks[track.track_id]
                self._tracks[track.track_id] = TrackRecord(
                    track_id=track.track_id,
                    name_en=existing.name_en or track.name_en,
                    name_zh=existing.name_zh or track.name_zh,
                    domain=existing.domain or track.domain,
                    category=existing.category or track.category,
                    sources=tuple(dict.fromkeys((*existing.sources, *track.sources))),
                )
                continue
            self._tracks[track.track_id] = track
        self._domains: dict[str, DomainRecord] = {}
        for domain in domains:
            if not isinstance(domain, DomainRecord):
                raise TypeError("Taxonomy expects DomainRecord instances")
            if not domain.domain_id:
                raise ValueError("domain_id must be a non-empty string")
            self._domains.setdefault(domain.domain_id, domain)
        if not self._tracks and not self._domains:
            raise ValueError("a taxonomy needs at least one track or domain")

    # -- construction --------------------------------------------------------
    @classmethod
    def from_synthetic(
        cls,
        tracks: Sequence[str | Mapping[str, Any] | TrackRecord] = (),
        domains: Sequence[str | Mapping[str, Any] | DomainRecord] = (),
    ) -> "Taxonomy":
        """Build a taxonomy from plain ids/mappings (tests need no config file)."""
        track_records: list[TrackRecord] = []
        for entry in tracks:
            if isinstance(entry, TrackRecord):
                track_records.append(entry)
            elif isinstance(entry, str):
                track_records.append(TrackRecord(track_id=entry, sources=("synthetic",)))
            elif isinstance(entry, Mapping):
                track_records.append(
                    TrackRecord(
                        track_id=str(entry.get("track_id") or entry.get("id") or ""),
                        name_en=entry.get("name_en"),
                        name_zh=entry.get("name_zh"),
                        domain=entry.get("domain"),
                        category=entry.get("category"),
                        sources=tuple(str(source) for source in entry.get("sources", ())) or ("synthetic",),
                    )
                )
            else:
                raise TypeError(f"unsupported synthetic track entry {entry!r}")
        domain_records: list[DomainRecord] = []
        for entry in domains:
            if isinstance(entry, DomainRecord):
                domain_records.append(entry)
            elif isinstance(entry, str):
                domain_records.append(DomainRecord(domain_id=entry))
            elif isinstance(entry, Mapping):
                domain_records.append(
                    DomainRecord(
                        domain_id=str(entry.get("domain_id") or entry.get("id") or ""),
                        name_en=entry.get("name_en"),
                        name_zh=entry.get("name_zh"),
                    )
                )
            else:
                raise TypeError(f"unsupported synthetic domain entry {entry!r}")
        return cls(tracks=track_records, domains=domain_records)

    @classmethod
    def from_config(cls, config_dir: str | os.PathLike[str] | None = None) -> "Taxonomy":
        """Load tracks + domains, and pick up track names from product codes."""
        directory = _resolve_config_dir(config_dir)
        tracks_path = directory / "tracks_device.json"
        if not tracks_path.exists():
            raise FileNotFoundError(f"missing taxonomy configuration {str(tracks_path)!r}")
        payload = _read_json(tracks_path)
        if not isinstance(payload, Mapping):
            raise ValueError(f"{tracks_path} must contain an object")
        tracks: list[TrackRecord] = []
        raw_tracks = payload.get("tracks")
        if isinstance(raw_tracks, Sequence) and not isinstance(raw_tracks, (str, bytes)):
            for entry in raw_tracks:
                if not isinstance(entry, Mapping):
                    continue
                track_id = str(entry.get("id") or entry.get("track_id") or "")
                if not track_id:
                    continue
                tracks.append(
                    TrackRecord(
                        track_id=track_id,
                        name_en=entry.get("name_en"),
                        name_zh=entry.get("name_zh"),
                        domain=entry.get("domain"),
                        category=entry.get("category"),
                        sources=("tracks_device.json",),
                    )
                )
        domains: list[DomainRecord] = []
        raw_domains = payload.get("domains")
        if isinstance(raw_domains, Sequence) and not isinstance(raw_domains, (str, bytes)):
            for entry in raw_domains:
                if not isinstance(entry, Mapping):
                    continue
                domain_id = str(entry.get("id") or entry.get("domain_id") or "")
                if not domain_id:
                    continue
                domains.append(
                    DomainRecord(
                        domain_id=domain_id,
                        name_en=entry.get("name_en"),
                        name_zh=entry.get("name_zh"),
                    )
                )

        known_tracks = {track.track_id for track in tracks}
        product_codes_path = directory / "product_code_tracks.json"
        added_from_codes: list[str] = []
        if product_codes_path.exists():
            product_codes = _read_json(product_codes_path)
            if isinstance(product_codes, Mapping):
                for value in product_codes.values():
                    if isinstance(value, str) and value and value not in known_tracks:
                        known_tracks.add(value)
                        added_from_codes.append(value)
                        tracks.append(
                            TrackRecord(
                                track_id=value,
                                sources=("product_code_tracks.json",),
                            )
                        )
        if not tracks and not domains:
            raise ValueError(
                f"{tracks_path} declared no tracks and no domains; a taxonomy of nothing "
                "would reject every output"
            )
        taxonomy = cls(tracks=tracks, domains=domains)
        # Exposed for a caller that wants to log *why* the vocabulary has an entry.
        taxonomy.added_track_ids_from_product_codes = tuple(added_from_codes)  # type: ignore[attr-defined]
        return taxonomy

    # -- queries -------------------------------------------------------------
    @property
    def track_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._tracks))

    @property
    def tracks(self) -> tuple[TrackRecord, ...]:
        return tuple(self._tracks[key] for key in self.track_ids)

    @property
    def domain_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._domains))

    @property
    def domains(self) -> tuple[DomainRecord, ...]:
        return tuple(self._domains[key] for key in self.domain_ids)

    def __len__(self) -> int:
        return len(self._tracks) + len(self._domains)

    def track(self, track_id: str) -> TrackRecord | None:
        return self._tracks.get(track_id)

    def domain(self, domain_id: str) -> DomainRecord | None:
        return self._domains.get(domain_id)

    def is_known_track(self, track_id: str) -> bool:
        return track_id in self._tracks

    def is_known_domain(self, domain_id: str) -> bool:
        return domain_id in self._domains

    def accepts_technology_domain(self, term: str) -> bool:
        """A ``technology_domains`` entry is declared iff it is a domain *or* a track.

        ``technology_domains`` is an open string array in the frozen schema.  The
        validator closes it against this configuration: the 23 declared domains
        are the primary vocabulary and the 50 declared tracks are accepted as the
        finer-grained terms the taxonomy already uses.  Nothing else is accepted.
        """
        return term in self._domains or term in self._tracks

    def domain_of_track(self, track_id: str) -> str | None:
        record = self._tracks.get(track_id)
        return record.domain if record else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "track_ids": list(self.track_ids),
            "domain_ids": list(self.domain_ids),
            "tracks": [self._tracks[key].to_dict() for key in self.track_ids],
            "domains": [self._domains[key].to_dict() for key in self.domain_ids],
        }
