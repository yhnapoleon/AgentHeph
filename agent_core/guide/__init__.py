"""Guide build pipeline (M2): UI facts -> UIInventory -> evidence -> topics -> cards ->
validate/review -> immutable KBRelease -> app_knowledge serving.

The external extractors (ts-morph / react-docgen / swagger-parser / Playwright) are Node
+ a running app; they are wired behind the fact contracts in facts.py. Everything from
normalization onward is pure Python and lives here.
"""
from agent_core.guide.evidence import EvidenceResolver, resolve_item
from agent_core.guide.facts import (
    ApiFacts,
    RuntimeFacts,
    SourceFacts,
    SourceRef,
)
from agent_core.guide.inventory import InventoryItem, UIInventory
from agent_core.guide.normalize import InventoryNormalizer, template_path

__all__ = [
    "SourceFacts", "ApiFacts", "RuntimeFacts", "SourceRef",
    "UIInventory", "InventoryItem",
    "InventoryNormalizer", "template_path",
    "EvidenceResolver", "resolve_item",
]
