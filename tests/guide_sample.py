"""Sample facts standing in for a small React 'issues' app, as if the extractors had run.
Plus a deterministic fake card drafter. Not collected by pytest (no test_ prefix)."""
from __future__ import annotations

from agent_core.guide.facts import (
    ApiFact,
    ApiFacts,
    ElementFact,
    FormFieldFact,
    RouteFact,
    RuntimeFacts,
    RuntimeObservation,
    SourceFacts,
    SourceRef,
    TransitionFact,
)

DOMAIN_MAP = {"issues": "issue_management", "runbook": "runbook"}

SOURCE = SourceFacts(
    routes=[
        RouteFact(route_pattern="/issues", page_component="IssuesPage", deeplink="/issues",
                  required_roles=["viewer", "bau_member"], menu_path=["Operations", "Issues"],
                  source_ref=SourceRef(type="code", file="routes.tsx", symbol="IssuesRoute")),
        RouteFact(route_pattern="/runbook", page_component="RunbookPage", deeplink="/runbook",
                  required_roles=["bau_member"], menu_path=["Operations", "Runbook"],
                  source_ref=SourceRef(type="code", file="routes.tsx", symbol="RunbookRoute")),
    ],
    elements=[
        ElementFact(page_component="IssuesPage", element_kind="heading", text="Issues (12)",
                    testid="issues-title", source_ref=SourceRef(type="code", file="IssuesPage.tsx")),
        ElementFact(page_component="IssuesPage", element_kind="tab", text="SLA risk only",
                    testid="sla-tab", source_ref=SourceRef(type="code", file="IssuesPage.tsx")),
    ],
    form_fields=[
        FormFieldFact(page_component="IssuesPage", field_name="status", label="Status",
                      enum=["open", "closed"], submit_target="listIssues",
                      source_ref=SourceRef(type="code", file="Filters.tsx")),
    ],
    transitions=[
        TransitionFact(page_component="IssuesPage", from_state="default",
                       action="enable 'SLA risk only'", to_state="filtered", origin="source",
                       source_ref=SourceRef(type="code", file="IssuesPage.tsx")),
    ],
)

API = ApiFacts(operations=[
    ApiFact(operation_id="listIssues", method="get", path="/issues",
            enums={"status": ["open", "closed", "resolved"]}),
])

RUNTIME = RuntimeFacts(observations=[
    RuntimeObservation(role="viewer", route_pattern="/issues", reached_testids=["issues-title", "sla-tab"],
                       scan_run="run-1"),
    RuntimeObservation(role="bau_member", route_pattern="/issues", reached_testids=["issues-title"],
                       scan_run="run-1"),
    RuntimeObservation(role="bau_member", route_pattern="/runbook", scan_run="run-1"),
])


def fake_drafter(kind: str, context: dict) -> dict:
    """Deterministic, clean-by-construction card text (no live ids/emails/timestamps)."""
    domain, cap = context["domain"], context["capability"]
    names = [f["name"] for f in context["facts"]
             if "=" not in f["name"] and not f["name"].startswith("/")]
    if kind == "howto":
        steps = "; ".join(f["name"] for f in context["facts"])
        body = f"To filter, {steps}."
    elif names:
        body = f"This {kind} explains {domain} {cap}: {', '.join(names)}."
    else:
        body = f"This {kind} explains {domain} {cap}."
    return {"title": f"{domain} {cap} {kind}", "body_md": body}
