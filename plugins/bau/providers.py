"""BAU as the first platform plugin — the four provider interfaces over BAU's existing
agent layer.

IMPORTANT — runtime boundary: these adapters import BAU's ``core.*`` modules (tools,
auth, knowledge), which live in the separate ``bau_center`` repo and need its database
and config. They therefore run only inside the BAU runtime environment; they are NOT
importable or testable from this repo's CI (bau_center is git-ignored). The M1
acceptance — "BAU behaves identically on agent_core" — is verified there, against BAU's
own regression suite, not here. This module is the wiring blueprint + shape contract.

Mapping (see design/ROADMAP.md M1.2):
  * BauTools        -> wraps ``core.agent.tools.build_langchain_tools(actor)``
  * BauDataScope    -> documents BAU's per-row scope, which is enforced INSIDE each tool's
                       query (``fn(session, actor, ...)`` -> ``_scoped_issue_query`` /
                       ``_accessible_*``). That source-side query scoping is the strong
                       layer; this adapter does not re-filter after the fact.
  * BauAuth         -> BAU role -> visible tools/areas
  * BauKnowledge    -> ``core.agent.knowledge.build_domain_card`` as a knowledge card

Integration note: BAU's ``build_langchain_tools`` already bakes in its own dedup +
runaway ``_run``. When fully integrated, governance must be unified (use the core
ToolGovernor over BAU's plain impl functions, OR keep BAU's and skip the core wrap) so
the runaway cap isn't effectively halved by double counting. Tracked for the BAU
migration; the core ToolGovernor is the intended home.
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

# Tools visible to non-elevated BAU users vs. the elevated tier. Authoritative
# visibility lives with BAU's role model; this is the platform-side projection.
_ELEVATED_ROLES = {"admin", "bau_member", "business_owner"}


def _to_current_user(principal: Principal):
    """Map a platform Principal onto BAU's ``CurrentUser`` (imported lazily so this
    module imports only inside the BAU runtime)."""
    from core.auth.jwt import CurrentUser

    return CurrentUser(
        username=principal.subject,
        user_id=int(principal.scopes[0]) if principal.scopes and principal.scopes[0].isdigit() else 0,
        role=(principal.roles[0] if principal.roles else "regular_user"),
        ad_groups=[r for r in principal.roles if not r.isdigit()],
    )


class BauTools(ToolProvider):
    def build_tools(self, principal: Principal, artifact_sink: list | None = None) -> list:
        from core.agent.tools import build_langchain_tools

        return build_langchain_tools(_to_current_user(principal), artifact_sink=artifact_sink)


class BauDataScope(DataScopeAdapter):
    """BAU enforces per-row scope at the source: every tool runs ``fn(session, actor,
    ...)`` and filters in the query (``_scoped_issue_query`` etc.). That is the strong
    layer required by the platform — there is no "fetch all then filter"."""

    def scope_query(self, query: Any, principal: Principal) -> Any:
        # No-op: scoping is injected inside each BAU tool's own query, not here.
        return query

    def post_filter(self, rows: list[Any], principal: Principal) -> list[Any]:
        # BAU has no post-fetch filtering because the query is already scoped.
        return rows


class BauAuth(AuthAdapter):
    def visible_areas(self, principal: Principal) -> set[str]:
        return {"issue_management", "runbook", "analytics"}

    def visible_tools(self, principal: Principal) -> set[str]:
        from core.agent.tools import build_langchain_tools

        names = {t.name for t in build_langchain_tools(_to_current_user(principal))}
        if _ELEVATED_ROLES & set(principal.roles):
            return names
        # Non-elevated users keep the read tools; live raw-API tools are elevated-only
        # (BAU rejects them at the tool layer too — defense in depth).
        return {n for n in names if not n.endswith("_get_raw")}


class BauKnowledge(KnowledgeProvider):
    def retrieve(self, area: str, principal: Principal, topic: str | None = None) -> list[dict]:
        from core.agent.knowledge import build_domain_card

        return [{
            "area": area, "topic": topic or "domain", "kind": "field",
            "title": "BAU domain glossary",
            "body_md": build_domain_card(compact=True),
            "source_refs": [{"type": "code", "file": "core/agent/knowledge.py"}],
        }]
