"""M2 Phase 5: a guide bot answers a turn over the frozen KB, on the M1 runtime.
Shows app_knowledge serving + per-actor area visibility through real tool execution."""
from __future__ import annotations

import pytest

pytest.importorskip("langgraph")

from agent_core.guide import KBPublisher, build_kb  # noqa: E402
from agent_core.guide.store import CardStore, GuideToolProvider  # noqa: E402
from agent_core.manifest import compute_manifest_digest  # noqa: E402
from agent_core.runtime import run_turn  # noqa: E402
from agent_core.schemas.identity import ExecutionContext, Principal  # noqa: E402
from agent_core.schemas.manifest import ChatbotManifest  # noqa: E402
from agent_core.schemas.sse import EventType  # noqa: E402
from tests.fakes import FakeToolModel, final_msg, tool_call_msg  # noqa: E402
from tests.guide_sample import API, DOMAIN_MAP, RUNTIME, SOURCE, fake_drafter  # noqa: E402

GUIDE_MANIFEST = ChatbotManifest.model_validate({
    "metadata": {"id": "guide-demo", "display_name": "Guide Demo"},
    "capabilities": ["guide"],
    "model": {"endpoint_ref": "x", "default": "m"},
    "tools": {"provider": "agent_core.guide.store.GuideToolProvider"},
    "rbac": {"principal_adapter": "x"},
})


def _store() -> CardStore:
    cards = build_kb(SOURCE, API, RUNTIME, drafter=fake_drafter, domain_map=DOMAIN_MAP).cards
    release = KBPublisher.freeze("guide-demo", cards, eval_passed=True, reviewer="alice")
    return CardStore(release)


def _run(principal, model):
    execution = ExecutionContext(
        deployment_id="guide-demo", manifest_digest=compute_manifest_digest(GUIDE_MANIFEST),
        run_id="r", thread_id="t")
    return list(run_turn(
        manifest=GUIDE_MANIFEST, provider=GuideToolProvider(_store()), principal=principal,
        execution=execution, message="how do I filter issues?", model=model))


def test_guide_answers_from_cards():
    model = FakeToolModel(responses=[
        tool_call_msg("app_knowledge", {"area": "issue_management"}, "c1"),
        final_msg("Open Issues and enable 'SLA risk only'."),
    ])
    events = _run(Principal(issuer="t", subject="m", roles=["bau_member"]), model)
    kinds = [e.event for e in events]
    assert EventType.tool_call in kinds and EventType.answer in kinds
    result = next(e for e in events if e.event is EventType.tool_result)
    assert "issue_management" in result.data["preview"]      # a real card came back


def test_viewer_cannot_reach_runbook_area():
    # viewer asks for runbook knowledge; the per-actor area set excludes it.
    model = FakeToolModel(responses=[
        tool_call_msg("app_knowledge", {"area": "runbook"}, "c1"),
        final_msg("That area isn't available to you."),
    ])
    events = _run(Principal(issuer="t", subject="v", roles=["viewer"]), model)
    result = next(e for e in events if e.event is EventType.tool_result)
    preview = result.data["preview"]
    assert "not-visible" in preview or "valid_values" in preview
    assert "runbook" not in preview.split("valid_values")[-1]   # runbook not offered as valid
