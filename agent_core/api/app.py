"""FastAPI app exposing the chat SSE contract.

One endpoint: ``POST /chat`` takes a ``ChatRequest`` (deployment_id + message), resolves
the deployment (and its immutable manifest_digest) server-side, builds the per-run
ExecutionContext, and streams ``run_turn`` as SSE — one ``EventEnvelope`` JSON per
``data:`` frame.

Principal resolution is pluggable via the ``get_principal`` dependency. M1 ships a
dev-header resolver (``X-Subject`` / ``X-Roles``); real auth / CredentialContext is M3.
Tests override this dependency to inject an actor.
"""
from __future__ import annotations

import json
import uuid
from typing import Iterator

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse

from agent_core.api.deployments import DeploymentRegistry
from agent_core.runtime import run_turn
from agent_core.schemas.identity import ExecutionContext, Principal
from agent_core.schemas.sse import ChatRequest, EventEnvelope


def get_principal(
    x_subject: str = Header(default=""),
    x_roles: str = Header(default=""),
) -> Principal:
    """Dev principal from headers. Replace via dependency override for real auth."""
    if not x_subject:
        raise HTTPException(status_code=401, detail="missing X-Subject")
    roles = [r.strip() for r in x_roles.split(",") if r.strip()]
    return Principal(issuer="dev-header", subject=x_subject, roles=roles)


def _sse(events: Iterator[EventEnvelope]) -> Iterator[str]:
    for ev in events:
        yield f"data: {json.dumps(ev.model_dump(mode='json'), ensure_ascii=False)}\n\n"


def create_app(registry: DeploymentRegistry) -> FastAPI:
    app = FastAPI(title="AgentHeph chat API")

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

    @app.post("/chat")
    def chat(req: ChatRequest, principal: Principal = Depends(get_principal)) -> StreamingResponse:
        deployment = registry.get(req.deployment_id)
        if deployment is None:
            raise HTTPException(status_code=404, detail="unknown deployment_id")

        execution = ExecutionContext(
            deployment_id=deployment.deployment_id,
            manifest_digest=deployment.manifest_digest,   # resolved server-side, immutable
            run_id=uuid.uuid4().hex,
            thread_id=(req.thread_id or "").strip() or uuid.uuid4().hex,
        )
        events = run_turn(
            manifest=deployment.manifest,
            provider=deployment.provider,
            principal=principal,
            execution=execution,
            message=req.message,
            model=deployment.model_factory(),
            auth_adapter=deployment.auth_adapter,
            resolved_slots=deployment.resolved_slots,
            audit_sink=deployment.audit_sink,
        )
        return StreamingResponse(_sse(events), media_type="text/event-stream")

    app.state.registry = registry
    return app
