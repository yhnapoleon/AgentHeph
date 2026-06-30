"""EvidenceResolver — assign an evidence status per item (a matrix, not a 0.73 score).

Triangulates the three branches. The rules (Guide §11) that keep it honest:
  * runtime presence is STRONG positive evidence; runtime absence is only WEAK negative
    (source-only items stay ``source_only``, they are not marked dead);
  * knip / a single deprecation signal alone cannot exclude (needs >= 2 stacked, and
    never if the thing was reached live);
  * a missing OpenAPI endpoint alone cannot mark dead;
  * ANY RBAC conflict (observed visibility broader than declared) goes to a human.
"""
from __future__ import annotations

from agent_core.guide.inventory import InventoryItem, UIInventory

VERIFIED = "verified"
SUPPORTED = "supported"
SOURCE_ONLY = "source_only"
RUNTIME_ONLY = "runtime_only"
CONFLICT = "conflict"
DEPRECATED_CANDIDATE = "deprecated_candidate"
EXCLUDED = "excluded"

DEPRECATION_THRESHOLD = 2  # a single signal (e.g. knip) is never enough


def _has(item: InventoryItem, ref_type: str) -> bool:
    return any(r.type == ref_type for r in item.source_refs)


def _reached_roles(item: InventoryItem) -> set[str]:
    return {role for role, reached in item.role_visibility.items() if reached}


def _rbac_conflict(item: InventoryItem) -> bool:
    """A role reached the item at runtime that the source did not declare as allowed —
    observed access is broader than declared. Only meaningful when roles are declared."""
    if not item.required_roles:
        return False
    return bool(_reached_roles(item) - set(item.required_roles))


def resolve_item(item: InventoryItem) -> str:
    if item.excluded:
        return EXCLUDED
    if _rbac_conflict(item):
        return CONFLICT

    has_code = _has(item, "code")
    has_api = _has(item, "openapi")
    reached = bool(_reached_roles(item))

    # Stacked deprecation on something never seen alive -> candidate (still human-reviewed).
    if item.deprecation_signals >= DEPRECATION_THRESHOLD and not reached:
        return DEPRECATED_CANDIDATE

    if has_code and reached:
        return VERIFIED
    if has_code and has_api:
        return SUPPORTED
    if has_code:
        return SOURCE_ONLY
    if reached:
        return RUNTIME_ONLY
    if has_api:
        return SUPPORTED          # contract evidence only; still reviewed per-card
    return CONFLICT               # no resolvable evidence


class EvidenceResolver:
    def resolve(self, inventory: UIInventory) -> UIInventory:
        for item in inventory.items:
            item.evidence_status = resolve_item(item)
        return inventory
