"""BAU plugin — built in M1.

Wraps bau_center's existing read tools as a ToolProvider, its domain knowledge as
a KnowledgeProvider, its actor-scoped queries as a DataScopeAdapter, and its roles
as an AuthAdapter. M1 acceptance: BAU behavior-equivalent on agent_core (full
regression), plus the write-consistency fix (atomic claim + idempotency + outbox).
"""
