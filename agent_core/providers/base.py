"""Provider interfaces (M0). An app plugs into the platform by implementing these.

Guide (M1/M2) implements KnowledgeProvider + AuthAdapter (visibility).
BAU (M1) implements ToolProvider + DataScopeAdapter + AuthAdapter.
Phase 2 implements the data/write ToolProviders and the per-row DataScopeAdapter.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from agent_core.schemas.identity import Principal


class ToolProvider(ABC):
    """Build the LangChain/MCP tool objects for this actor, scoped to identity.
    Each tool runs with the principal's identity and must apply the same scoping
    as the app's own UI (see DataScopeAdapter)."""

    @abstractmethod
    def build_tools(self, principal: Principal, artifact_sink: list | None = None) -> list[Any]:
        ...


class KnowledgeProvider(ABC):
    """Fetch knowledge cards for a partition (the guide KB lives behind this)."""

    @abstractmethod
    def retrieve(self, area: str, principal: Principal, topic: str | None = None) -> list[dict]:
        ...


class AuthAdapter(ABC):
    """Visibility layer: which areas / tools this principal may see. Used at
    graph-build time to trim the tool/area enum per actor."""

    @abstractmethod
    def visible_areas(self, principal: Principal) -> set[str]:
        ...

    @abstractmethod
    def visible_tools(self, principal: Principal) -> set[str]:
        ...


class DataScopeAdapter(ABC):
    """Per-row data authorization. M0 defines the interface only.

    IMPORTANT (Codex review): row-level scoping must be enforced where the data
    lives — query-level scope injection or PostgreSQL RLS — NOT by fetching
    everything and filtering afterward (that leaks counts/sums/ordering and lets
    unauthorized data into the process). ``post_filter`` is defense-in-depth, the
    LAST line, never the primary defense. See ROADMAP M3 (three layers).
    """

    @abstractmethod
    def scope_query(self, query: Any, principal: Principal) -> Any:
        """Inject the principal's scope INTO the query before it executes."""
        ...

    @abstractmethod
    def post_filter(self, rows: list[Any], principal: Principal) -> list[Any]:
        """Defense-in-depth check on returned rows. Never the only defense."""
        ...
