"""CardValidator (deterministic eval gate) + tiered review classifier.

The deterministic checks (Guide §14) are the cheap, non-LLM gate that blocks release:
schema valid; provenance present; no live business data / secrets in prose; visibility
not broadened beyond evidence; related_tools exist and aren't deprecated; how-to cards
are backed by transition evidence. LLM fuzzy checks and the guide-bot golden regression
layer on top (the regression reuses the M1 eval gate).

``classify_review`` implements the batch-vs-per-card tiering (Guide §13).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from agent_core.guide.cards import CARD_KINDS, KnowledgeCard

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_ISO_TS = re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
_ID_REF = re.compile(r"#\d+")
_SECRET = re.compile(r"\b(token|password|bearer|authorization|secret|api[_-]?key)\b", re.IGNORECASE)


@dataclass
class CardCheck:
    card_topic: str
    failures: list[str]

    @property
    def ok(self) -> bool:
        return not self.failures


class CardValidator:
    def validate(
        self,
        card: KnowledgeCard,
        *,
        allowed_roles: set[str] | None = None,
        known_tools: set[str] | None = None,
        deprecated_tools: set[str] | None = None,
    ) -> CardCheck:
        f: list[str] = []

        # schema / required fields
        if card.kind not in CARD_KINDS:
            f.append(f"unknown card kind: {card.kind}")
        if not card.title.strip() or not card.body_md.strip():
            f.append("empty title or body")
        if not card.area or not card.topic:
            f.append("missing area/topic key")

        # provenance: every card must be traceable
        if not card.source_refs:
            f.append("no source_refs (not traceable)")

        # no live data / secrets in user-facing prose
        if _EMAIL.search(card.body_md):
            f.append("body contains an email address (live data)")
        if _ISO_TS.search(card.body_md):
            f.append("body contains a timestamp (live data)")
        if _ID_REF.search(card.body_md):
            f.append("body contains an id reference like #123 (live data)")
        if _SECRET.search(card.body_md):
            f.append("body contains a secret-like keyword")

        # visibility may not exceed what evidence supports
        if allowed_roles is not None and not set(card.visible_to) <= allowed_roles:
            f.append(f"visible_to exceeds evidence: {sorted(set(card.visible_to) - allowed_roles)}")

        # related_tools must exist and must not be deprecated
        if known_tools is not None and not set(card.related_tools) <= known_tools:
            f.append(f"related_tools not found: {sorted(set(card.related_tools) - known_tools)}")
        if deprecated_tools and set(card.related_tools) & deprecated_tools:
            f.append(f"references deprecated tools: {sorted(set(card.related_tools) & deprecated_tools)}")

        # how-to must be backed by evidence and not be a conflict
        if card.kind == "howto" and card.evidence_status in ("", "conflict"):
            f.append("how-to card lacks resolved transition evidence")

        return CardCheck(card_topic=card.topic, failures=f)

    def validate_all(self, cards: list[KnowledgeCard], **kw) -> tuple[bool, list[CardCheck]]:
        checks = [self.validate(c, **kw) for c in cards]
        return all(c.ok for c in checks), checks


# ---- tiered review (Guide §13) ----
_SENSITIVE_TRIGGERS = {"conflict", "source_only", "runtime_only", "deprecated_candidate"}


@dataclass
class ReviewDecision:
    card_topic: str
    tier: str            # "batch" | "per_card"
    reasons: list[str]


def classify_review(card: KnowledgeCard) -> ReviewDecision:
    """Batch approval only if everything holds; any trigger forces per-card review."""
    reasons: list[str] = []
    if card.evidence_status in _SENSITIVE_TRIGGERS:
        reasons.append(f"evidence_status={card.evidence_status}")
    if not card.source_refs:
        reasons.append("no source_refs")
    if card.evidence_status != "verified":
        reasons.append("not verified")
    # how-to with action steps gets a closer look (could embed a submit/modify step).
    if card.kind == "howto":
        reasons.append("how-to (action steps)")
    tier = "batch" if not reasons else "per_card"
    return ReviewDecision(card_topic=card.topic, tier=tier, reasons=reasons)
