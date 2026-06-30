"""Runtime engine (M1): manifest -> ReAct graph -> governed tools -> SSE stream.

Ports the BAU chat runtime onto agent_core:
  * governance — exact dedup + runaway cap, enforced centrally (governance.py)
  * prompt — hard-coded discipline skeleton + manifest slots (prompt.py)
  * llm — manifest-driven OpenAI-compatible factory (llm.py)
  * graph — visibility-trimmed, governed ReAct agent (graph.py)
  * stream — SSE EventEnvelope mapping with call_id pairing (stream.py)
  * checkpoint / audit — thread key + MemorySaver, per-turn AgentRun (checkpoint.py, audit.py)

Public surface kept small; import submodules for the rest.
"""
from agent_core.runtime.audit import AgentRunRecord, AuditSink, InMemoryAuditSink
from agent_core.runtime.governance import ToolGovernor
from agent_core.runtime.stream import run_turn

__all__ = ["run_turn", "ToolGovernor", "AgentRunRecord", "AuditSink", "InMemoryAuditSink"]
