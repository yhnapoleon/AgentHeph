"""M0-remainder: the FastAPI /chat SSE endpoint streams the contract end to end.
Uses the demo deployment + a scripted fake model (no gateway)."""
from __future__ import annotations

import json

import pytest

pytest.importorskip("langgraph")
pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from agent_core.api import Deployment, DeploymentRegistry, create_app, get_principal  # noqa: E402
from agent_core.manifest import load_manifest  # noqa: E402
from agent_core.schemas.identity import Principal  # noqa: E402
from plugins.demo.providers import DemoAuth, DemoTools  # noqa: E402
from tests.fakes import FakeToolModel, final_msg, tool_call_msg  # noqa: E402
from tests.test_runtime_stream import MANIFEST  # noqa: E402


def _fresh_model() -> FakeToolModel:
    return FakeToolModel(responses=[
        tool_call_msg("list_tickets", {"status": "open"}, "call-1"),
        final_msg("You have 1 open ticket."),
    ])


def _client() -> TestClient:
    registry = DeploymentRegistry()
    registry.register(Deployment(
        deployment_id="demo",
        manifest=load_manifest(MANIFEST),
        provider=DemoTools(),
        model_factory=_fresh_model,
        auth_adapter=DemoAuth(),
    ))
    app = create_app(registry)
    app.dependency_overrides[get_principal] = lambda: Principal(
        issuer="test", subject="alice", roles=["member"])
    return TestClient(app)


def _parse_sse(body: str) -> list[dict]:
    return [json.loads(line[len("data: "):]) for line in body.splitlines()
            if line.startswith("data: ")]


def test_chat_endpoint_streams_contract():
    resp = _client().post("/chat", json={"deployment_id": "demo", "message": "open tickets?"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(resp.text)
    kinds = [e["event"] for e in events]
    assert kinds[0] == "meta" and kinds[-1] == "done"
    assert "tool_call" in kinds and "answer" in kinds
    # every frame carries the run/thread ids and a server seq
    assert [e["seq"] for e in events] == list(range(len(events)))
    assert all(e["run_id"] and e["thread_id"] for e in events)


def test_unknown_deployment_404():
    resp = _client().post("/chat", json={"deployment_id": "nope", "message": "hi"})
    assert resp.status_code == 404


def test_missing_principal_401():
    registry = DeploymentRegistry()
    registry.register(Deployment(
        deployment_id="demo", manifest=load_manifest(MANIFEST),
        provider=DemoTools(), model_factory=_fresh_model, auth_adapter=DemoAuth()))
    # no dependency override -> dev-header resolver runs and rejects the missing header
    resp = TestClient(create_app(registry)).post(
        "/chat", json={"deployment_id": "demo", "message": "hi"})
    assert resp.status_code == 401
