"""Device Intelligence: applications, device identities, product families and their evidence.

The module keeps four different things apart, because conflating them is how a product catalogue
becomes fiction:

* a **regulatory record** is one row in an FDA dataset (510(k), PMA original, PMA supplement, recall);
* a **regulatory application** is an official identifier (a K number, a PMA number, a supplement id);
* a **device identity** is the specific device an application cleared or approved;
* a **product family** is a set of devices/versions whose relationship is *evidenced* - in this
  release only the PMA application hierarchy qualifies.

MedRadar identifiers are internal and always prefixed; they never impersonate an FDA identifier.
"""
from .build import DeviceIndex, build_index
from .identifiers import FAMILY_PREFIX, APPLICATION_PREFIX, DEVICE_PREFIX, relation_types
from .model import (
    Application,
    DeviceIdentity,
    DeviceRelation,
    EvidenceRef,
    ProductFamily,
    RecallRecord,
    RELATION_STATUSES,
)
from .quality import quality_report

__all__ = [
    "APPLICATION_PREFIX",
    "DEVICE_PREFIX",
    "FAMILY_PREFIX",
    "RELATION_STATUSES",
    "Application",
    "DeviceIdentity",
    "DeviceIndex",
    "DeviceRelation",
    "EvidenceRef",
    "ProductFamily",
    "RecallRecord",
    "build_index",
    "quality_report",
    "relation_types",
]
