"""Tiny in-memory dataset for the demo plugin. Stands in for an app's data source so
the runtime can be exercised end-to-end without any external system."""
from __future__ import annotations

# owner == a Principal.subject; status is a small enum.
TICKETS: list[dict] = [
    {"id": 1, "title": "Login page 500", "owner": "alice", "status": "open"},
    {"id": 2, "title": "Export CSV slow", "owner": "alice", "status": "closed"},
    {"id": 3, "title": "Webhook retries", "owner": "bob", "status": "open"},
    {"id": 4, "title": "SSO timeout", "owner": "bob", "status": "open"},
]

KNOWLEDGE: dict[str, list[dict]] = {
    "tickets": [
        {
            "area": "tickets",
            "topic": "statuses",
            "kind": "enum",
            "title": "Ticket statuses",
            "body_md": "A ticket is `open` (needs work) or `closed` (resolved).",
            "related_tools": ["list_tickets"],
            "source_refs": [{"type": "code", "file": "plugins/demo/data.py"}],
        }
    ],
}
