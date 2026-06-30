"""M1.4: the eval gate runs golden assertions against the bot and blocks promote on any
failure. Uses scripted models per question (deterministic) to exercise the wiring."""
from __future__ import annotations

import pytest

pytest.importorskip("langgraph")

from agent_core.eval import gate, make_turn_runner  # noqa: E402
from agent_core.manifest import compute_manifest_digest, load_manifest  # noqa: E402
from agent_core.schemas.identity import ExecutionContext, Principal  # noqa: E402
from evals.demo_golden import DEMO_GOLDEN  # noqa: E402
from plugins.demo.providers import DemoAuth, DemoTools  # noqa: E402
from tests.fakes import FakeToolModel, final_msg, tool_call_msg  # noqa: E402
from tests.test_runtime_stream import MANIFEST  # noqa: E402


def _execution(manifest) -> ExecutionContext:
    return ExecutionContext(
        deployment_id="demo", manifest_digest=compute_manifest_digest(manifest),
        run_id="r", thread_id="t",
    )


def _runner(model_for):
    manifest = load_manifest(MANIFEST)
    return make_turn_runner(
        manifest=manifest, provider=DemoTools(),
        principal=Principal(issuer="t", subject="alice", roles=["member"]),
        execution=_execution(manifest), model_for=model_for, auth_adapter=DemoAuth(),
    )


def _good_model(question: str) -> FakeToolModel:
    if "delete" in question:
        return FakeToolModel(responses=[final_msg("I can't delete tickets — I only read.")])
    return FakeToolModel(responses=[
        tool_call_msg("list_tickets", {"status": "open"}, "c1"),
        final_msg("You have 1 open ticket: Login page 500 (#1)."),
    ])


def test_gate_passes_when_assertions_hold():
    result = gate(DEMO_GOLDEN, _runner(_good_model))
    assert result.passed, [f.failures for f in result.failures]
    assert len(result.results) == len(DEMO_GOLDEN)


def test_gate_blocks_on_scope_leak():
    # A bot that leaks another user's ticket title must fail the scope assertion.
    def leaky(question: str) -> FakeToolModel:
        if "delete" in question:
            return FakeToolModel(responses=[final_msg("I can't, I only read.")])
        return FakeToolModel(responses=[
            tool_call_msg("list_tickets", {"status": "open"}, "c1"),
            final_msg("Open: Login page 500, and also Webhook retries (#3)."),  # leaks bob's
        ])

    result = gate(DEMO_GOLDEN, _runner(leaky))
    assert not result.passed
    failed_ids = {r.case_id for r in result.failures}
    assert "open-tickets-routing-and-scope" in failed_ids


def test_gate_blocks_on_missing_tool_route():
    # Answering "open tickets" from thin air (no list_tickets call) must fail routing.
    def no_tool(question: str) -> FakeToolModel:
        return FakeToolModel(responses=[final_msg("Everything looks fine.")])

    result = gate(DEMO_GOLDEN, _runner(no_tool))
    assert not result.passed
