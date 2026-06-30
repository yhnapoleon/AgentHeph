"""KnowledgeCard schema + CardGenerator.

A card has two readers: ``body_md`` explains to the user; ``related_tools`` + field/enum
semantics let the agent act. Generation is schema-constrained: the LLM (injected
``drafter``) only writes ``title``/``body_md`` from NORMALIZED facts — never the raw repo
— while the generator fills the structured fields and enforces the red line:

  **How-to steps may use only evidenced transitions.** A how-to card is built solely from
  ``transition`` items (which ARE evidence); if a topic has none, no how-to card is
  produced. The drafter never sees free text to invent steps from.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from typing import Callable

from pydantic import BaseModel, Field

from agent_core.guide.cluster import Topic
from agent_core.guide.inventory import InventoryItem

CARD_KINDS = ("feature", "navigation", "field", "enum", "howto")

# most-cautious-wins ranking, so a card is only as strong as its weakest item.
_CONCERN = {
    "verified": 0, "supported": 1, "source_only": 2, "runtime_only": 3,
    "deprecated_candidate": 4, "conflict": 5, "excluded": 6, "": 5,
}


class KnowledgeCard(BaseModel):
    area: str                      # = domain
    topic: str
    kind: str
    title: str
    body_md: str
    visible_to: list[str] = Field(default_factory=list)
    related_tools: list[str] = Field(default_factory=list)
    source_refs: list[dict] = Field(default_factory=list)
    evidence_status: str = ""

    def content_hash(self) -> str:
        payload = self.model_dump(exclude={"source_refs"})
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# drafter(kind, context) -> {"title": str, "body_md": str}; context has only normalized facts.
Drafter = Callable[[str, dict], dict]


def _weakest(items: list[InventoryItem]) -> str:
    return max((i.evidence_status for i in items), key=lambda s: _CONCERN.get(s, 5), default="")


def _visible_to(items: list[InventoryItem]) -> list[str]:
    declared: set[str] = set()
    reached: set[str] = set()
    for i in items:
        declared.update(i.required_roles)
        reached.update(r for r, ok in i.role_visibility.items() if ok)
    # Prefer declared visibility; fall back to roles that actually reached it. Never
    # broaden beyond evidence — CardValidator re-checks this.
    return sorted(declared or reached)


def _related_tools(items: list[InventoryItem]) -> list[str]:
    tools: set[str] = set()
    for i in items:
        tools.update(i.api_bindings)
    return sorted(tools)


def _aggregate_refs(items: list[InventoryItem]) -> list[dict]:
    out: list[dict] = []
    seen: set[tuple] = set()
    for i in items:
        for r in i.source_refs:
            d = dataclasses.asdict(r)
            key = tuple(sorted(d.items()))
            if key not in seen:
                seen.add(key)
                out.append(d)
    return out


def _facts(items: list[InventoryItem]) -> list[dict]:
    # only normalized, non-live attrs reach the drafter.
    return [{"kind": i.kind, "name": i.name, "attrs": i.attrs} for i in items]


class CardGenerator:
    def __init__(self, drafter: Drafter):
        self.drafter = drafter

    def _card(self, kind: str, topic: Topic, items: list[InventoryItem]) -> KnowledgeCard:
        drafted = self.drafter(kind, {
            "kind": kind, "domain": topic.domain, "capability": topic.capability,
            "facts": _facts(items),
        })
        return KnowledgeCard(
            area=topic.domain, topic=f"{topic.topic}.{kind}", kind=kind,
            title=drafted["title"], body_md=drafted["body_md"],
            visible_to=_visible_to(items), related_tools=_related_tools(items),
            source_refs=_aggregate_refs(items), evidence_status=_weakest(items),
        )

    def generate(self, topic: Topic) -> list[KnowledgeCard]:
        by_kind: dict[str, list[InventoryItem]] = {}
        for it in topic.items:
            by_kind.setdefault(it.kind, []).append(it)

        cards: list[KnowledgeCard] = []
        if by_kind.get("page"):
            cards.append(self._card("navigation", topic, by_kind["page"]))
        for fld in by_kind.get("form_field", []):
            related = [fld] + [e for e in by_kind.get("enum", [])
                               if e.attrs.get("field") == fld.name]
            cards.append(self._card("field", topic, related))
        # enum cards grouped by field
        enums_by_field: dict[str, list[InventoryItem]] = {}
        for e in by_kind.get("enum", []):
            enums_by_field.setdefault(e.attrs.get("field", ""), []).append(e)
        for field_name, evals in enums_by_field.items():
            if field_name:
                cards.append(self._card("enum", topic, evals))
        # how-to ONLY from evidenced transitions; else a feature card from elements.
        if by_kind.get("transition"):
            cards.append(self._card("howto", topic, by_kind["transition"]))
        elif by_kind.get("element"):
            cards.append(self._card("feature", topic, by_kind["element"]))
        return cards
