# Studio frontend (scaffold)

The **single SSE renderer** reused by every bot: it renders the chat **contract** event
stream ([src/contract.ts](src/contract.ts) mirrors `agent_core/schemas/sse.py`), not any
per-app UI. One renderer, all deployments — a deployment is selected by `deployment_id`.

This is an M1 scaffold (files only; not yet `npm install`-ed). To run against the
FastAPI backend:

```bash
# backend (serves POST /chat as SSE) — wire create_app(registry) under uvicorn
# frontend:
cd studio/frontend
npm install
npm run dev        # Vite proxies /chat -> http://localhost:8000
```

`src/sseClient.ts` reads the `text/event-stream` body of `POST /chat` and yields one
`EventEnvelope` per frame; the renderer ignores unknown event types so additive contract
changes never break it. Auth is a dev header (`X-Subject`/`X-Roles`) for now — real auth
is M3.
