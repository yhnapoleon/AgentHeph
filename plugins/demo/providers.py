"""Demo plugin: the four provider interfaces over an in-memory dataset.

Purpose — exercise the runtime end-to-end (tools, per-row scope, visibility, knowledge,
SSE) with zero external dependencies. It is the reference implementation a real plugin
copies the shape of. The per-row scope here is the differentiator demonstrated small:
a non-admin only ever sees rows they own, enforced **before** the tool returns them.
"""
from __future__ import annotations

from typing import Any

from agent_core.providers.base import (
    AuthAdapter,
    DataScopeAdapter,
    KnowledgeProvider,
    ToolProvider,
)
from agent_core.schemas.identity import Principal

from plugins.demo.data import KNOWLEDGE, TICKETS

_ALL_TOOLS = {"list_tickets", "get_ticket", "app_knowledge"}


def _is_admin(principal: Principal) -> bool:
    return "admin" in principal.roles


class DemoDataScope(DataScopeAdapter):
    """Per-row scope: admins see all rows; everyone else sees only rows they own.

    ``scope_query`` filters at the source (the tool only ever receives scoped rows);
    ``post_filter`` re-checks the same rule as defense-in-depth (never the only line)."""

    def scope_query(self, query: list[dict], principal: Principal) -> list[dict]:
        if _is_admin(principal):
            return list(query)
        return [r for r in query if r.get("owner") == principal.subject]

    def post_filter(self, rows: list[Any], principal: Principal) -> list[Any]:
        if _is_admin(principal):
            return rows
        return [r for r in rows if r.get("owner") == principal.subject]


class DemoAuth(AuthAdapter):
    def visible_areas(self, principal: Principal) -> set[str]:
        return set(KNOWLEDGE)

    def visible_tools(self, principal: Principal) -> set[str]:
        return set(_ALL_TOOLS)


class DemoKnowledge(KnowledgeProvider):
    def retrieve(self, area: str, principal: Principal, topic: str | None = None) -> list[dict]:
        cards = KNOWLEDGE.get(area, [])
        if topic:
            cards = [c for c in cards if c.get("topic") == topic]
        return cards


class DemoTools(ToolProvider):
    def __init__(self, scope: DemoDataScope | None = None, knowledge: DemoKnowledge | None = None):
        self.scope = scope or DemoDataScope()
        self.knowledge = knowledge or DemoKnowledge()

    def build_tools(self, principal: Principal, artifact_sink: list | None = None) -> list:
        from langchain_core.tools import StructuredTool

        def list_tickets(status: str = "") -> list:
            """List tickets visible to you. Optional status filter: open | closed."""
            rows = self.scope.scope_query(TICKETS, principal)
            if status:
                rows = [r for r in rows if r["status"] == status]
            return self.scope.post_filter(rows, principal)

        def get_ticket(ticket_id: int) -> dict:
            """Get one ticket by id (only if you are allowed to see it)."""
            rows = self.scope.scope_query(TICKETS, principal)
            for r in rows:
                if r["id"] == ticket_id:
                    return r
            return {"error": "ticket not found or not visible"}

        def app_knowledge(area: str, topic: str = "") -> list:
            """Look up how-to / field / enum knowledge cards for an area."""
            return self.knowledge.retrieve(area, principal, topic=topic or None)

        return [
            StructuredTool.from_function(list_tickets),
            StructuredTool.from_function(get_ticket),
            StructuredTool.from_function(app_knowledge),
        ]
