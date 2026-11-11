"""Canonical entity structures for ATLAS-ID.

These dataclasses are the *contract* between connectors, the store and the
graph.  They are intentionally small: an entity holds identity, not analysis.

Key modelling decisions (see ``docs/atlas/IDENTITY_MODEL.md``)
-------------------------------------------------------------
* ``Company`` is a legal/business group.  ``Manufacturer`` is the entity that
  actually made the device, which may be a subsidiary, a contract manufacturer,
  or a historical name.  They are never collapsed into one table row.
* ``Device`` is a *regulatory product record*, not a marketing concept.  One
  brand can be many Device rows (one per DI/model); one Device row can carry
  several identifiers of different schemes.
* ``Identifier`` always carries its scheme, issuer and jurisdiction scope.  A
  DI, a 510(k) number, a Canadian licence number, a model number and a product
  code are five different kinds of thing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .normalize import SCHEMES

ENTITY_TYPES = frozenset({"company", "manufacturer", "device", "product_family", "identifier"})

#: Official identifier schemes.  A *model number* is deliberately absent: it is
#: a manufacturer-assigned display attribute, not a registry identifier, and is
#: stored on the device instead.
OFFICIAL_SCHEMES = frozenset(
    {"di", "basic_udi_di", "510k", "pma", "denovo", "licence_no", "mdall_device_id", "mdall_company_id", "duns", "nct", "doi", "pmid", "patent_no", "ocid"}
)


class IdentityError(ValueError):
    """Raised when an entity violates the identity contract."""


@dataclass(frozen=True)
class Identifier:
    scheme: str
    value: str
    issuer: str = ""
    scope: str = ""
    is_primary: bool = False
    note: str = ""

    def __post_init__(self) -> None:
        if self.scheme not in SCHEMES:
            raise IdentityError(f"unknown identifier scheme: {self.scheme!r}")
        if not self.value:
            raise IdentityError(f"identifier {self.scheme!r} has an empty value")

    @property
    def key(self) -> str:
        return f"{self.scheme}:{self.value}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "scheme": self.scheme,
            "value": self.value,
            "issuer": self.issuer or SCHEMES[self.scheme]["issuer"],
            "scope": self.scope or SCHEMES[self.scheme]["scope"],
            "is_primary": self.is_primary,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Identifier":
        return cls(
            scheme=str(payload["scheme"]),
            value=str(payload["value"]),
            issuer=str(payload.get("issuer") or ""),
            scope=str(payload.get("scope") or ""),
            is_primary=bool(payload.get("is_primary")),
            note=str(payload.get("note") or ""),
        )


@dataclass
class Company:
    """A legal/business group (parent), not a manufacturing site."""

    company_id: str
    canonical_name: str
    country: str = ""
    legal_form: str = ""
    valid_from: str = ""
    valid_to: str = ""
    former_names: list[str] = field(default_factory=list)
    subsidiaries: list[str] = field(default_factory=list)
    external_ids: dict[str, str] = field(default_factory=dict)
    parent_company_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.company_id:
            raise IdentityError("company_id is required")
        if not self.canonical_name.strip():
            raise IdentityError("canonical_name is required")

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class Manufacturer:
    """The legal manufacturer / brand owner / registration holder in a record."""

    manufacturer_id: str
    name: str
    company_id: str = ""
    role: str = "legal_manufacturer"  # legal_manufacturer | brand_owner | registration_holder
    country: str = ""
    site: str = ""
    relationship: str = "subsidiary"  # subsidiary | parent | contract | legacy_name | unknown
    valid_from: str = ""
    valid_to: str = ""

    def __post_init__(self) -> None:
        if not self.manufacturer_id:
            raise IdentityError("manufacturer_id is required")
        if not self.name.strip():
            raise IdentityError("manufacturer name is required")
        if self.role not in {"legal_manufacturer", "brand_owner", "registration_holder"}:
            raise IdentityError(f"unknown manufacturer role: {self.role!r}")

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class Device:
    """One regulatory product record: a device/model as a registry knows it."""

    device_id: str
    canonical_name: str
    brand_name: str = ""
    model_number: str = ""
    catalog_number: str = ""
    product_family: str = ""
    device_class: str = ""
    product_codes: list[str] = field(default_factory=list)
    markets: list[str] = field(default_factory=list)
    manufacturer_id: str = ""
    company_id: str = ""
    identifiers: list[Identifier] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.device_id:
            raise IdentityError("device_id is required")
        if not self.canonical_name.strip():
            raise IdentityError("canonical_name is required for a device")
        for ident in self.identifiers:
            if not isinstance(ident, Identifier):
                raise IdentityError("device identifiers must be Identifier instances")
        seen = [i.key for i in self.identifiers]
        if len(seen) != len(set(seen)):
            raise IdentityError(f"{self.device_id}: duplicate identifier")

    def identifiers_of(self, scheme: str) -> list[str]:
        return [i.value for i in self.identifiers if i.scheme == scheme]

    def to_dict(self) -> dict[str, Any]:
        payload = dict(self.__dict__)
        payload["identifiers"] = [i.to_dict() for i in self.identifiers]
        return payload


__all__ = [
    "Company",
    "Device",
    "ENTITY_TYPES",
    "IdentityError",
    "Identifier",
    "Manufacturer",
    "OFFICIAL_SCHEMES",
]
