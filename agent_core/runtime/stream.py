"""Run one turn and emit the SSE contract as ``EventEnvelope`` objects.

This is where the BAU ``_events_for_message`` bug is fixed: tool_call/tool_result are
paired by **call_id** (the model's ``tool_calls[].id`` and the ToolMessage's
``tool_call_id``), not by tool name — so parallel calls to the same tool pair correctly.

The mapping is otherwise faithful to BAU's contract: ``meta -> tool_call* ->
tool_result* -> artifact* -> answer -> (error) -> done``. The final assistant text is
held and emitted last (after every tool event), and a per-server ``seq`` is the
authoritative ordering.
"""
from __future__ import annotations

from typing import Iterator

from agent_core.providers.base import AuthAdapter, ToolProvider
from agent_core.runtime.audit import AgentRunRecord, AuditSink
from agent_core.runtime.checkpoint import thread_key
from agent_core.runtime.governance import ToolGovernor
from agent_core.schemas.identity import ExecutionContext, Principal
from agent_core.schemas.manifest import ChatbotManifest
from agent_core.schemas.sse import EventEnvelope, EventType


def _text_content(msg) -> str:
    content = getattr(msg, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # provider may return content blocks
        return "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return str(content)


def _raw_events(msg) -> Iterator[tuple[EventType, dict]]:
    """Map one LangChain message to (event_type, data) pairs. The final answer is
    marked with event ``answer`` here but held by the caller and emitted last."""
    msg_type = getattr(msg, "type", "")
    if msg_type == "ai":
        for call in getattr(msg, "tool_calls", None) or []:
            yield EventType.tool_call, {
                "call_id": call.get("id", ""),          # <- the pairing key (was missing)
                "tool": call.get("name", ""),
                "args_preview": call.get("args", {}),
            }
        text = _text_content(msg)
        if text:
            yield EventType.answer, {"text": text}
    elif msg_type == "tool":
        yield EventType.tool_result, {
            "call_id": getattr(msg, "tool_call_id", "") or "",   # <- pairs to the call
            "tool": getattr(msg, "name", "") or "",
            "preview": _text_content(msg)[:500],
        }


def run_turn(
    *,
    manifest: ChatbotManifest,
    provider: ToolProvider,
    principal: Principal,
    execution: ExecutionContext,
    message: str,
    model,
    governor: ToolGovernor | None = None,
    auth_adapter: AuthAdapter | None = None,
    resolved_slots: dict[str, str] | None = None,
    artifact_sink: list | None = None,
    audit_sink: AuditSink | None = None,
) -> Iterator[EventEnvelope]:
    """One conversational turn -> stream of contract events.

    ``execution`` carries the immutable run_id/thread_id/deployment_id/manifest_digest
    resolved server-side. ``model`` is injected (the LLM factory is wired at the API
    layer) so this is unit-testable with a fake model.
    """
    from agent_core.runtime.graph import build_agent

    governor = governor or ToolGovernor(
        per_tool_call_limit=manifest.tools.governance.per_tool_call_limit,
        dedup_exact_repeats=manifest.tools.governance.dedup_exact_repeats,
    )
    artifact_sink = [] if artifact_sink is None else artifact_sink
    seq = 0

    def env(event: EventType, data: dict) -> EventEnvelope:
        nonlocal seq
        ev = EventEnvelope(
            event=event, run_id=execution.run_id, thread_id=execution.thread_id,
            seq=seq, data=data,
        )
        seq += 1
        return ev

    yield env(EventType.meta, {"thread_id": execution.thread_id})

    answer = ""
    tool_calls: list[str] = []
    try:
        agent = build_agent(
            manifest, provider, principal, governor=governor, artifact_sink=artifact_sink,
            auth_adapter=auth_adapter, resolved_slots=resolved_slots, model=model,
        )
        config = {"configurable": {"thread_id": thread_key(principal, execution, execution.thread_id)}}
        for update in agent.stream({"messages": [("human", message)]}, config, stream_mode="updates"):
            for _node, payload in (update or {}).items():
                for msg in (payload or {}).get("messages", []) or []:
                    for event, data in _raw_events(msg):
                        if event is EventType.answer:
                            answer = data["text"]            # hold; emit last
                        else:
                            if event is EventType.tool_call:
                                tool_calls.append(data["tool"])
                            yield env(event, data)
            while artifact_sink:
                yield env(EventType.artifact, artifact_sink.pop(0))
        yield env(EventType.answer, {"text": answer})
    except Exception as exc:  # noqa: BLE001 - surface as a contract error event
        _audit(audit_sink, manifest, execution, principal, message, answer, tool_calls, str(exc))
        yield env(EventType.error, {"message": str(exc)})
        yield env(EventType.done, {})
        return

    _audit(audit_sink, manifest, execution, principal, message, answer, tool_calls, None)
    yield env(EventType.done, {})


def _audit(audit_sink, manifest, execution, principal, message, answer, tool_calls, error):
    if audit_sink is None:
        return
    try:
        audit_sink.record(AgentRunRecord(
            deployment_id=execution.deployment_id, manifest_digest=execution.manifest_digest,
            run_id=execution.run_id, thread_id=execution.thread_id, subject=principal.subject,
            question=message[:2000], answer=(answer or "")[:8000],
            tool_calls=tool_calls, error=error,
        ))
    except Exception:  # noqa: BLE001 - auditing must never break a turn
        pass
