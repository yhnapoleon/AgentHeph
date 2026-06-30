"""Build-time pipeline glue: facts -> inventory -> evidence -> topics -> cards.

A thin convenience over the stages so callers (Studio orchestration, tests) get one
entry point. Review, eval gate, and freeze are deliberately separate steps the caller
runs explicitly — they involve humans and a go/no-go decision.
"""
from __future__ import annotations

from dataclasses import dataclass

from agent_core.guide.cards import CardGenerator, Drafter, KnowledgeCard
from agent_core.guide.cluster import Topic, TopicPlanner, TopicRefiner
from agent_core.guide.evidence import EvidenceResolver
from agent_core.guide.facts import ApiFacts, RuntimeFacts, SourceFacts
from agent_core.guide.inventory import UIInventory
from agent_core.guide.normalize import InventoryNormalizer


@dataclass
class PipelineResult:
    inventory: UIInventory
    topics: list[Topic]
    cards: list[KnowledgeCard]


def build_kb(
    source: SourceFacts,
    api: ApiFacts,
    runtime: RuntimeFacts,
    *,
    drafter: Drafter,
    domain_map: dict[str, str] | None = None,
    refiner: TopicRefiner | None = None,
) -> PipelineResult:
    inventory = InventoryNormalizer().merge(source, api, runtime)
    EvidenceResolver().resolve(inventory)
    topics = TopicPlanner(domain_map=domain_map, refiner=refiner).plan(inventory)
    gen = CardGenerator(drafter)
    cards: list[KnowledgeCard] = []
    for topic in topics:
        cards.extend(gen.generate(topic))
    return PipelineResult(inventory=inventory, topics=topics, cards=cards)
