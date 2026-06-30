# AgentHeph

Platform for generating app-specific chatbots (guide / read-only assistant / edit) from a
declarative **manifest**, on a reusable runtime core. Generalized from BAU Center.

> Design docs live in [`design/`](design/) (PLATFORM_DESIGN, MVP_DESIGN, ROADMAP, architecture HTML).
> `bau_center/` is a **separate reference repo** (git-ignored here), used as the first plugin / acceptance oracle.

## Layout

| Dir | Purpose | Status |
|---|---|---|
| `agent_core/` | Runtime core: schemas (contracts), provider interfaces, runtime, eval harness | M0 (schemas) → M1 (runtime) |
| `studio/` | Control plane (build chatbots) | M2+ |
| `plugins/` | Per-app providers (first: BAU) | M1 |
| `contracts/` | Exported JSON Schemas (generated) | M0 |
| `evals/` | Golden sets per deployment | M1+ |
| `tests/` | Schema + contract tests | M0 |

## Roadmap (see `design/ROADMAP.md`)

`M0 contracts → M1 core + BAU plugin (behavior-equivalent) → M2 guide vertical → M3 phase-2 (foundation/readonly/edit) → M4 diff & self-loop`.

## Dev

```bash
python -m venv .venv && . .venv/Scripts/activate   # Windows
pip install -e ".[dev]"
pytest
python -m contracts.generate_schemas               # export JSON Schemas
```
