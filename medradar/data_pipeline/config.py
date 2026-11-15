"""Configuration for the continuous FDA pipeline.

All credentials are read from the environment or a mode-checked file. They are never
written to the manifest, the ledger, logs or request evidence. The public product only
needs the path to the active snapshot, not the API key.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PIPELINE_VERSION = "medradar-data-pipeline/1.0.0"
DEFAULT_API_BASE = "https://api.fda.gov"
DEFAULT_USER_AGENT = "MedRadar/1.0 (medical technology intelligence; +https://github.com/ChazY11/medradar)"
DEFAULT_ROOT = Path(os.environ.get("MEDRADAR_PIPELINE_ROOT", "data/data_pipeline"))


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.environ.get(name)
    if raw in (None, ""):
        return default
    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError(name + " must be an integer") from error
    if value < minimum:
        raise ValueError(name + " must be at least " + str(minimum))
    return value


def _env_float(name: str, default: float, minimum: float = 0.0) -> float:
    raw = os.environ.get(name)
    if raw in (None, ""):
        return default
    try:
        value = float(raw)
    except ValueError as error:
        raise ValueError(name + " must be a number") from error
    if value < minimum:
        raise ValueError(name + " must be at least " + str(minimum))
    return value


def load_api_key() -> str | None:
    """Read the key from the environment or a local mode-checked file.

    The key file path comes from MEDRADAR_OPENFDA_KEY_FILE. A world-readable file is
    refused; the error states the permission problem without printing the key.
    """
    value = os.environ.get("OPENFDA_API_KEY") or os.environ.get("MEDRADAR_OPENFDA_API_KEY")
    if value is not None:
        value = value.strip()
        return value or None
    path_value = os.environ.get("MEDRADAR_OPENFDA_KEY_FILE")
    if not path_value:
        return None
    path = Path(path_value)
    try:
        mode = path.stat().st_mode & 0o777
    except OSError as error:
        raise ValueError("cannot stat MEDRADAR_OPENFDA_KEY_FILE: " + str(error)) from error
    if mode & 0o077:
        raise ValueError(
            "MEDRADAR_OPENFDA_KEY_FILE must not be group/world readable (mode "
            + oct(mode)
            + ")"
        )
    key = path.read_text(encoding="utf-8").strip()
    return key or None


@dataclass
class Settings:
    root: Path = field(default_factory=lambda: DEFAULT_ROOT)
    api_base: str = DEFAULT_API_BASE
    user_agent: str = DEFAULT_USER_AGENT
    api_key: str | None = field(default=None, repr=False)
    timeout_seconds: int = 90
    retries: int = 4
    requests_per_minute: int = 60
    daily_request_limit: int | None = None
    review_db: Path | None = None
    registry_path: Path | None = None
    retention_snapshots: int = 4
    min_free_bytes: int = 2 * 1024 * 1024 * 1024
    max_record_drop_ratio: float = 0.02
    max_record_drop_floor: int = 0
    removal_confirmations: int = 2
    missing_recheck_cap: int = 50
    source_degraded_after: int = 3
    validation_build_device_index: bool = True

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        if self.api_key is None:
            self.api_key = load_api_key()
        if self.daily_request_limit is None:
            self.daily_request_limit = 100000 if self.api_key else 900
        if self.review_db is None:
            configured = os.environ.get("MEDRADAR_REVIEW_DB")
            self.review_db = Path(configured) if configured else Path("data") / "identity" / "review.db"

    @property
    def snapshots_dir(self) -> Path:
        return self.root / "snapshots"

    @property
    def staging_dir(self) -> Path:
        return self.root / "staging"

    @property
    def state_db(self) -> Path:
        return self.root / "pipeline.db"

    @property
    def active_pointer(self) -> Path:
        return self.root / "active.json"

    @property
    def lock_path(self) -> Path:
        return self.root / "pipeline.lock"

    @property
    def log_dir(self) -> Path:
        return self.root / "logs"

    def ensure(self) -> "Settings":
        for directory in (self.root, self.snapshots_dir, self.staging_dir, self.log_dir):
            directory.mkdir(parents=True, exist_ok=True)
        return self

    @classmethod
    def from_env(cls, root: Path | str | None = None) -> "Settings":
        resolved_root = Path(root) if root is not None else DEFAULT_ROOT
        return cls(
            root=resolved_root,
            api_base=os.environ.get("MEDRADAR_OPENFDA_BASE", DEFAULT_API_BASE).rstrip("/"),
            timeout_seconds=_env_int("MEDRADAR_OPENFDA_TIMEOUT", 90),
            retries=_env_int("MEDRADAR_OPENFDA_RETRIES", 4, 0),
            requests_per_minute=_env_int("MEDRADAR_OPENFDA_RPM", 60),
            daily_request_limit=(
                _env_int("MEDRADAR_PIPELINE_DAILY_LIMIT", 900) if not load_api_key() else
                _env_int("MEDRADAR_PIPELINE_DAILY_LIMIT", 100000)
            ),
            retention_snapshots=_env_int("MEDRADAR_PIPELINE_RETENTION", 4),
            min_free_bytes=_env_int("MEDRADAR_PIPELINE_MIN_FREE_BYTES", 2 * 1024 * 1024 * 1024),
            max_record_drop_ratio=_env_float("MEDRADAR_PIPELINE_MAX_DROP_RATIO", 0.02),
            removal_confirmations=_env_int("MEDRADAR_PIPELINE_REMOVAL_CONFIRMATIONS", 2),
            missing_recheck_cap=_env_int("MEDRADAR_PIPELINE_RECHECK_CAP", 50),
        )
