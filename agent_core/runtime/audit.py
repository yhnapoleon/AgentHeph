"""Audit trail for one turn (AgentRun). Best-effort: auditing must never break a turn.

The runtime emits an ``AgentRunRecord`` per turn to an ``AuditSink``. The default sink
is in-memory (tests / dev); a plugin or deployment wires a DB-backed sink. This mirrors
BAU's ``AgentRun`` row (kind / user / question / answer / tool calls) without coupling
agent_core to any particular ORM.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class AgentRunRecord:
    deployment_id: str
    manifest_digest: str
    run_id: str
    thread_id: str
    subject: str
    question: str
    answer: str = ""
    tool_calls: list[str] = field(default_factory=list)
    error: str | None = None


class AuditSink(Protocol):
    def record(self, run: AgentRunRecord) -> None: ...


class InMemoryAuditSink:
    """Default sink: keeps records in a list. Useful in tests and as a base to copy."""

    def __init__(self) -> None:
        self.runs: list[AgentRunRecord] = []

    def record(self, run: AgentRunRecord) -> None:
        self.runs.append(run)
