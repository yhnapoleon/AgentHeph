"""UIInventory — the unified intermediate model the three branches normalize into.

The design states the conceptual tree (Domain -> Capability -> Page -> UI State ->
Element|FormField|Transition|RoleVisibility|ApiBinding). We store it as a flat list of
``InventoryItem`` (each carrying its key path) because per-item normalization, dedup,
content-hashing, and evidence resolution are far cleaner on a flat list; the tree is a
projection (``UIInventory.tree``) over these items.

Every item keeps provenance (``source_refs``), a stable ``content_hash`` (for UI-diff),
and — once EvidenceResolver runs — an ``evidence_status``.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from agent_core.guide.facts import SourceRef

ITEM_KINDS = ("page", "element", "form_field", "enum", "transition")


def _hash(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class InventoryItem:
    kind: str                       # one of ITEM_KINDS
    domain: str                     # business domain (set during topic planning; "" until then)
    capability: str                 # capability within the domain
    page: str                       # route_pattern the item lives on
    name: str                       # element text / field name / enum value / transition action
    attrs: dict = field(default_factory=dict)            # kind-specific payload
    required_roles: list[str] = field(default_factory=list)     # from source (declared)
    role_visibility: dict[str, bool] = field(default_factory=dict)  # role -> reached at runtime
    api_bindings: list[str] = field(default_factory=list)        # operation_ids
    source_refs: list[SourceRef] = field(default_factory=list)
    deprecation_signals: int = 0
    excluded: bool = False                               # human exclusion
    evidence_status: str = ""                            # filled by EvidenceResolver

    def identity(self) -> tuple:
        """Stable identity for dedup/merge: kind + key path + name."""
        return (self.kind, self.page, self.name, self.capability)

    def content_hash(self) -> str:
        """Hash of the semantic content (NOT provenance/evidence) so the same UI element
        hashes equally across scans; drives UI-diff."""
        return _hash({
            "kind": self.kind, "domain": self.domain, "capability": self.capability,
            "page": self.page, "name": self.name, "attrs": self.attrs,
            "required_roles": sorted(self.required_roles),
            "api_bindings": sorted(self.api_bindings),
        })


@dataclass
class UIInventory:
    items: list[InventoryItem] = field(default_factory=list)
    # digests frozen at build time (repo commit, openapi digest, scan plan, ...)
    digests: dict = field(default_factory=dict)

    def by_kind(self, kind: str) -> list[InventoryItem]:
        return [i for i in self.items if i.kind == kind]

    def roles(self) -> set[str]:
        rs: set[str] = set()
        for it in self.items:
            rs.update(it.required_roles)
            rs.update(it.role_visibility)
        return rs

    def tree(self) -> dict:
        """Projection back to Domain -> Capability -> Page -> items (for review UIs)."""
        out: dict = {}
        for it in self.items:
            (out.setdefault(it.domain or "_", {})
                .setdefault(it.capability or "_", {})
                .setdefault(it.page or "_", [])
                .append(it))
        return out
