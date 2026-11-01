"""Evidence-preserving cross-domain company resolution."""
from __future__ import annotations

from typing import Any

from ...config import CompanyRegistry, load_companies


class CrossDomainCompanyResolver:
    def __init__(self, registry: CompanyRegistry | None = None) -> None:
        self.registry = registry or load_companies("device")

    def supplier(self, legal_name: str) -> dict[str, Any]:
        key, confidence, alias = self.registry.resolve(legal_name)
        return {
            "company_key": key, "confidence": confidence, "matched_alias": alias,
            "method": "curated_contiguous_alias" if key else "unmatched",
            "evidence": legal_name,
        }

    def sec_cik(self, ticker_map: dict[str, str], company_key: str) -> str | None:
        company = self.registry.get(company_key)
        ticker = str((company or {}).get("ticker") or "").upper()
        return ticker_map.get(ticker)
