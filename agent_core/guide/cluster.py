"""TopicPlanner — cluster inventory items into knowledge topics.

Keys knowledge on ``domain / capability / topic`` (a business view), NOT on page/tab
names — a UI page is only a ``source_ref``, so a UI refactor doesn't shift the whole KB
(ROADMAP M2.4). The navigation tree (route first-segment + menu path) is the seed; an
injected ``refiner`` (the LLM, human-reviewed) may re-key topics. The deterministic seed
here is what tests pin; the LLM only refines.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from agent_core.guide.inventory import InventoryItem, UIInventory

# item kind -> the business capability bucket it seeds.
_CAPABILITY_BY_KIND = {
    "page": "navigation",
    "element": "navigation",
    "form_field": "configuration",
    "enum": "configuration",
    "transition": "workflow",
}


@dataclass
class Topic:
    domain: str
    capability: str
    topic: str
    items: list[InventoryItem] = field(default_factory=list)


# A refiner may merge/split/re-key topics (the LLM step). Identity by default.
TopicRefiner = Callable[[list[Topic]], list[Topic]]


def _first_segment(route: str) -> str:
    parts = [p for p in route.split("/") if p and not p.startswith("{")]
    return parts[0] if parts else "app"


class TopicPlanner:
    def __init__(self, domain_map: dict[str, str] | None = None, refiner: TopicRefiner | None = None):
        # domain_map renames a raw route segment to a business domain (e.g. issues ->
        # issue_management); unmapped segments pass through.
        self.domain_map = domain_map or {}
        self.refiner = refiner

    def plan(self, inventory: UIInventory) -> list[Topic]:
        groups: dict[tuple, Topic] = {}
        for it in inventory.items:
            if it.excluded:
                continue
            domain = self.domain_map.get(_first_segment(it.page), _first_segment(it.page))
            capability = _CAPABILITY_BY_KIND.get(it.kind, "usage")
            # write the business keys back onto the item (page stays as source_ref).
            it.domain = domain
            it.capability = capability
            key = (domain, capability)
            topic = groups.get(key)
            if topic is None:
                topic = Topic(domain=domain, capability=capability, topic=f"{domain}.{capability}")
                groups[key] = topic
            topic.items.append(it)

        topics = list(groups.values())
        return self.refiner(topics) if self.refiner else topics
