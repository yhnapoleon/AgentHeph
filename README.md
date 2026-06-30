# AgentHeph

Platform for generating app-specific chatbots (guide / read-only assistant / edit) from a
declarative **manifest**, on a reusable runtime core. Generalized from BAU Center.

> Design docs live in [`design/`](design/) (PLATFORM_DESIGN, MVP_DESIGN, ROADMAP, architecture HTML).
> `bau_center/` is a **separate reference repo** (git-ignored here), used as the first plugin / acceptance oracle.

## Layout

| Dir | Purpose | Status |
|---|---|---|
| `agent_core/schemas/` | Contracts: manifest, SSE, identity, effect (Pydantic) | M0 |
| `agent_core/manifest/` | Manifest loader + immutable digest | M0 |
| `agent_core/providers/` | Plugin interfaces (Tool/Knowledge/Auth/DataScope) | M0 |
| `agent_core/runtime/` | Governed ReAct graph, SSE stream (call_id), prompt, llm, checkpoint, audit | M1 |
| `agent_core/api/` | FastAPI `/chat` SSE app + deployment registry | M1 |
| `agent_core/write/` | Consistency-correct write-proposal store (claim + outbox + idempotency) | M1 |
| `agent_core/eval/` | Assertion harness + runtime runner/gate | M0/M1 |
| `plugins/` | Per-app providers: `demo` (reference) + `bau` (blueprint) | M1 |
| `studio/frontend/` | Single SSE renderer (Vite + React + TS) | M1 scaffold |
| `contracts/` | Exported JSON Schemas + `fixtures/` (BAU + second app) | M0 |
| `migrations/` | Alembic (write-flow tables) | M1 |
| `evals/`, `tests/` | Golden sets; schema/SSE/runtime/write/eval tests | M0/M1 |

## Roadmap (see `design/ROADMAP.md`)

`M0 contracts → M1 core + BAU plugin (behavior-equivalent) → M2 guide vertical → M3 phase-2 (foundation/readonly/edit) → M4 diff & self-loop`.

## Dev

```bash
python -m venv .venv && . .venv/Scripts/activate   # Windows
pip install -e ".[dev]"
pytest
python -m contracts.generate_schemas               # export JSON Schemas
```
