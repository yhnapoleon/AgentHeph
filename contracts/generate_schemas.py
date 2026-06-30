"""Export Pydantic contracts to JSON Schema.

Run: ``python -m contracts.generate_schemas`` (from repo root).
The generated ``*.schema.json`` are the language-neutral contract the frontend
and other services validate against.
"""
from __future__ import annotations

import json
import pathlib

from agent_core.schemas.manifest import ChatbotManifest
from agent_core.schemas.sse import ChatRequest, EventEnvelope

OUT = pathlib.Path(__file__).parent


def main() -> None:
    models = {
        "manifest": ChatbotManifest,
        "chat_request": ChatRequest,
        "event_envelope": EventEnvelope,
    }
    for name, model in models.items():
        path = OUT / f"{name}.schema.json"
        path.write_text(
            json.dumps(model.model_json_schema(by_alias=True), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"wrote {path.name}")


if __name__ == "__main__":
    main()
