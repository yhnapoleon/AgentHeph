"""Conversation memory: thread key + checkpointer.

The thread key is built server-side and embeds tenant / deployment / subject and binds
the manifest digest, so:
  * one user can never resume another user's thread (subject is in the key), and
  * a thread started under one bot version does not resume on a different config
    (digest is in the key) — matching the SSE contract's thread-key rule.

M1 uses an in-process ``MemorySaver`` (durable Postgres checkpoint is deferred to M3b,
and only if the write flow moves onto LangGraph ``interrupt()`` — see ROADMAP).
"""
from __future__ import annotations

from agent_core.schemas.identity import ExecutionContext, Principal

_checkpointer = None


def thread_key(principal: Principal, execution: ExecutionContext, thread_id: str) -> str:
    """Stable, namespaced checkpoint key. ``manifest_digest`` is included so a bot
    upgrade does not silently resume an old conversation on new config."""
    tenant = principal.tenant_id or "_"
    return (
        f"{tenant}/{execution.deployment_id}/{principal.subject}"
        f"/{thread_id}@{execution.manifest_digest}"
    )


def get_checkpointer():
    """Process-wide in-memory checkpointer (lazy import so agent_core imports without
    langgraph installed)."""
    global _checkpointer
    if _checkpointer is None:
        from langgraph.checkpoint.memory import MemorySaver

        _checkpointer = MemorySaver()
    return _checkpointer
