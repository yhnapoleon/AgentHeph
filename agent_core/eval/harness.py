"""Minimal eval harness (M0 skeleton).

Golden cases are **assertion sets**, not prose gold answers (a prose gold for a
tool-using bot carries its own fabrication risk). Tool-call checks are
deterministic; an LLM judge (added later) only scores fuzzy phrasing.

Gates (deployment-blocking) reference these assertion kinds:
  no_fabrication, scope_respected, correct_tool_routing, (phase 2) write_requires_confirm.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class ToolTrajectoryAssertion:
    must_call: list[str] = field(default_factory=list)
    must_not_call: list[str] = field(default_factory=list)


@dataclass
class ScopeAssertion:
    forbidden_substrings: list[str] = field(default_factory=list)


@dataclass
class NoFabricationAssertion:
    # For a known-absent fact, the answer must admit it instead of inventing.
    must_contain_any: list[str] = field(default_factory=list)


@dataclass
class GoldenCase:
    id: str
    question: str
    tool_trajectory: ToolTrajectoryAssertion | None = None
    scope: ScopeAssertion | None = None
    no_fabrication: NoFabricationAssertion | None = None


@dataclass
class CaseResult:
    case_id: str
    passed: bool
    failures: list[str] = field(default_factory=list)


class TurnRunner(Protocol):
    """Runs one turn; returns (answer_text, tool_calls_made)."""

    def __call__(self, question: str) -> tuple[str, list[str]]: ...


def evaluate_case(case: GoldenCase, runner: TurnRunner) -> CaseResult:
    answer, tool_calls = runner(case.question)
    failures: list[str] = []

    if case.tool_trajectory:
        for t in case.tool_trajectory.must_call:
            if t not in tool_calls:
                failures.append(f"expected tool '{t}' not called")
        for t in case.tool_trajectory.must_not_call:
            if t in tool_calls:
                failures.append(f"forbidden tool '{t}' was called")

    if case.scope:
        for s in case.scope.forbidden_substrings:
            if s in answer:
                failures.append(f"out-of-scope substring leaked: '{s}'")

    if case.no_fabrication:
        if not any(p in answer for p in case.no_fabrication.must_contain_any):
            failures.append("answer did not admit 'not recorded' for a known-absent fact")

    return CaseResult(case_id=case.id, passed=not failures, failures=failures)


def evaluate_all(cases: list[GoldenCase], runner: TurnRunner) -> list[CaseResult]:
    return [evaluate_case(c, runner) for c in cases]
