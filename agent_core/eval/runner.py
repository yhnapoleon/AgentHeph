"""Wire the assertion harness to a real deployment turn.

The harness (harness.py) checks assertion sets — tool trajectory, scope, no-fabrication
— deterministically. This adapter runs a golden question through ``run_turn`` and
extracts ``(answer_text, tool_calls)`` for those assertions, then ``gate`` turns the
results into a promote/block decision (no gate pass => no promote, per ROADMAP §12).

``model_for`` lets a caller pick the model per question — production ignores the
question and returns the real LLM; tests script a deterministic model per case.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from agent_core.eval.harness import CaseResult, GoldenCase, TurnRunner, evaluate_all
from agent_core.providers.base import AuthAdapter, ToolProvider
from agent_core.runtime.stream import run_turn
from agent_core.schemas.identity import ExecutionContext, Principal
from agent_core.schemas.manifest import ChatbotManifest
from agent_core.schemas.sse import EventType


def make_turn_runner(
    *,
    manifest: ChatbotManifest,
    provider: ToolProvider,
    principal: Principal,
    execution: ExecutionContext,
    model_for: Callable[[str], object],
    auth_adapter: AuthAdapter | None = None,
) -> TurnRunner:
    """Build a TurnRunner that drives one ``run_turn`` per question and returns
    ``(answer_text, tool_calls)`` for the assertions."""

    def run(question: str) -> tuple[str, list[str]]:
        events = list(run_turn(
            manifest=manifest, provider=provider, principal=principal, execution=execution,
            message=question, model=model_for(question), auth_adapter=auth_adapter,
        ))
        answer = ""
        tool_calls: list[str] = []
        for ev in events:
            if ev.event is EventType.answer:
                answer = ev.data.get("text", "")
            elif ev.event is EventType.tool_call:
                tool_calls.append(ev.data.get("tool", ""))
        return answer, tool_calls

    return run


@dataclass
class GateResult:
    passed: bool
    results: list[CaseResult]

    @property
    def failures(self) -> list[CaseResult]:
        return [r for r in self.results if not r.passed]


def gate(cases: list[GoldenCase], runner: TurnRunner) -> GateResult:
    """Run every golden case; the gate passes only if ALL pass (a single failure blocks
    promote — matching the 'no partial promote' rule)."""
    results = evaluate_all(cases, runner)
    return GateResult(passed=all(r.passed for r in results), results=results)
