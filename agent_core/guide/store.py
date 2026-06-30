"""Runtime KB serving: card store + the providers the guide bot consumes.

Reads an immutable KBRelease. Visibility is enforced PER ACTOR at retrieval time: a card
is returned only if it is public (no ``visible_to``) or its ``visible_to`` intersects the
principal's roles (admins see all). The ``app_knowledge`` tool's area set is therefore
dynamic per actor — a user can't even discover an area they can't see.

(Storage here is in-memory keyed by area; production swaps in PostgreSQL + FTS behind
the same retrieve() surface, per design §16.)
"""
from __future__ import annotations

from agent_core.guide.cards import KnowledgeCard
from agent_core.guide.publish import KBRelease
from agent_core.providers.base import KnowledgeProvider, ToolProvider
from agent_core.schemas.identity import Principal


def _is_admin(principal: Principal) -> bool:
    return "admin" in principal.roles


def _visible(card: KnowledgeCard, principal: Principal) -> bool:
    if _is_admin(principal) or not card.visible_to:
        return True
    return bool(set(card.visible_to) & set(principal.roles))


class CardStore:
    def __init__(self, release: KBRelease):
        self.release = release
        self._by_area: dict[str, list[KnowledgeCard]] = {}
        for c in release.cards:
            self._by_area.setdefault(c.area, []).append(c)

    def visible_areas(self, principal: Principal) -> set[str]:
        return {area for area, cards in self._by_area.items()
                if any(_visible(c, principal) for c in cards)}

    def retrieve(self, area: str, principal: Principal, topic: str | None = None) -> list[KnowledgeCard]:
        cards = [c for c in self._by_area.get(area, []) if _visible(c, principal)]
        if topic:
            cards = [c for c in cards if topic in c.topic]
        return cards


class GuideKnowledgeProvider(KnowledgeProvider):
    def __init__(self, store: CardStore):
        self.store = store

    def retrieve(self, area: str, principal: Principal, topic: str | None = None) -> list[dict]:
        return [c.model_dump() for c in self.store.retrieve(area, principal, topic=topic)]


class GuideToolProvider(ToolProvider):
    """Builds the guide's read-only tools: ``app_knowledge`` (area-scoped card lookup)
    and ``nav_deeplink`` (where-is-a-feature). The area set is the actor's visible areas."""

    def __init__(self, store: CardStore):
        self.store = store

    def build_tools(self, principal: Principal, artifact_sink: list | None = None) -> list:
        from langchain_core.tools import StructuredTool

        store = self.store
        visible = sorted(store.visible_areas(principal))

        def app_knowledge(area: str, topic: str = "") -> list | dict:
            """Look up knowledge cards for an area (feature/field/enum/navigation/how-to)."""
            if area not in visible:
                return {"error": f"unknown or not-visible area: {area!r}", "valid_values": visible}
            cards = store.retrieve(area, principal, topic=topic or None)
            return [{"topic": c.topic, "kind": c.kind, "title": c.title, "body_md": c.body_md,
                     "related_tools": c.related_tools} for c in cards]

        def nav_deeplink(area: str) -> list | dict:
            """Return deep links for navigation cards in an area (where a feature lives)."""
            if area not in visible:
                return {"error": f"unknown or not-visible area: {area!r}", "valid_values": visible}
            out = []
            for c in store.retrieve(area, principal):
                if c.kind == "navigation":
                    for ref in c.source_refs:
                        pass  # deeplink is carried in body/source; kept simple for M2 scaffold
                    out.append({"topic": c.topic, "title": c.title})
            return out

        # area enum is advertised in the description so the model discovers it cheaply.
        app_knowledge.__doc__ += f"\nVisible areas: {visible}."
        return [
            StructuredTool.from_function(app_knowledge),
            StructuredTool.from_function(nav_deeplink),
        ]
