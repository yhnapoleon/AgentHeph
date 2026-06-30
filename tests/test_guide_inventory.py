"""M2 Phase 1: normalization + the evidence matrix."""
from __future__ import annotations

from agent_core.guide import (
    ApiFacts,
    EvidenceResolver,
    InventoryNormalizer,
    RuntimeFacts,
    SourceFacts,
    template_path,
)
from agent_core.guide.evidence import (
    CONFLICT,
    DEPRECATED_CANDIDATE,
    EXCLUDED,
    RUNTIME_ONLY,
    SOURCE_ONLY,
    SUPPORTED,
    VERIFIED,
    resolve_item,
)
from agent_core.guide.facts import (
    ApiFact,
    ElementFact,
    FormFieldFact,
    RouteFact,
    RuntimeObservation,
    SourceRef,
)
from agent_core.guide.inventory import InventoryItem


def test_path_templating():
    assert template_path("/issues/123") == "/issues/{id}"
    assert template_path("/issues/9f8c2a1b4d5e/edit") == "/issues/{id}/edit"
    assert template_path("/issues") == "/issues"


def test_normalize_maps_facts_and_strips_dynamic_label():
    source = SourceFacts(
        routes=[RouteFact(route_pattern="/issues/123", page_component="IssuesPage",
                          deeplink="/issues", required_roles=["viewer"],
                          source_ref=SourceRef(type="code", file="routes.tsx"))],
        elements=[ElementFact(page_component="IssuesPage", element_kind="heading",
                              text="Issues (12)", testid="issues-title",
                              source_ref=SourceRef(type="code", file="IssuesPage.tsx"))],
        form_fields=[FormFieldFact(page_component="IssuesPage", field_name="status",
                                   enum=["open", "closed"], submit_target="listIssues",
                                   source_ref=SourceRef(type="code", file="Filters.tsx"))],
    )
    inv = InventoryNormalizer().merge(source, ApiFacts(), RuntimeFacts())

    page = inv.by_kind("page")[0]
    assert page.page == "/issues/{id}"                      # templated
    heading = inv.by_kind("element")[0]
    assert heading.attrs["text"] == "Issues"                # count stripped
    enums = {i.attrs["value"] for i in inv.by_kind("enum")}
    assert enums == {"open", "closed"}


def test_normalize_merges_api_enums_and_runtime_visibility():
    source = SourceFacts(
        routes=[RouteFact(route_pattern="/issues", page_component="IssuesPage",
                          required_roles=["viewer", "bau_member"],
                          source_ref=SourceRef(type="code", file="routes.tsx"))],
        form_fields=[FormFieldFact(page_component="IssuesPage", field_name="status",
                                   submit_target="listIssues",
                                   source_ref=SourceRef(type="code"))],
    )
    api = ApiFacts(operations=[ApiFact(operation_id="listIssues", method="get", path="/issues",
                                       enums={"status": ["open", "closed", "resolved"]})])
    runtime = RuntimeFacts(observations=[
        RuntimeObservation(role="viewer", route_pattern="/issues", scan_run="run-1"),
    ])
    inv = EvidenceResolver().resolve(InventoryNormalizer().merge(source, api, runtime))

    # API enum values landed as enum items.
    assert {"open", "closed", "resolved"} <= {i.attrs["value"] for i in inv.by_kind("enum")}
    # the page was reached by viewer at runtime -> verified.
    page = inv.by_kind("page")[0]
    assert page.role_visibility.get("viewer") is True
    assert page.evidence_status == VERIFIED


def _item(**kw) -> InventoryItem:
    base = dict(kind="page", domain="", capability="X", page="/x", name="/x")
    base.update(kw)
    return InventoryItem(**base)


def test_evidence_matrix_statuses():
    code = [SourceRef(type="code", file="a.tsx")]
    api = [SourceRef(type="openapi", operation_id="op")]
    rt = [SourceRef(type="runtime", scan_run="r", role="viewer")]

    # verified: source + reached at runtime
    assert resolve_item(_item(source_refs=code, role_visibility={"viewer": True})) == VERIFIED
    # source_only: source, never reached (runtime absence is only weak negative)
    assert resolve_item(_item(source_refs=code)) == SOURCE_ONLY
    # supported: source + api, no runtime
    assert resolve_item(_item(source_refs=code + api)) == SUPPORTED
    # runtime_only: reached but source mapping failed
    assert resolve_item(_item(source_refs=rt, role_visibility={"viewer": True})) == RUNTIME_ONLY


def test_evidence_rbac_conflict_goes_to_human():
    # declared viewer-only, but bau_member reached it at runtime -> conflict
    item = _item(source_refs=[SourceRef(type="code")], required_roles=["viewer"],
                 role_visibility={"bau_member": True})
    assert resolve_item(item) == CONFLICT


def test_evidence_deprecation_needs_two_signals_and_no_runtime():
    code = [SourceRef(type="code")]
    # one signal (e.g. knip alone) is not enough -> stays source_only
    assert resolve_item(_item(source_refs=code, deprecation_signals=1)) == SOURCE_ONLY
    # two stacked signals, never reached -> candidate
    assert resolve_item(_item(source_refs=code, deprecation_signals=2)) == DEPRECATED_CANDIDATE
    # but runtime presence is strong positive -> not deprecated despite signals
    assert resolve_item(_item(source_refs=code, deprecation_signals=3,
                              role_visibility={"viewer": True})) == VERIFIED


def test_evidence_excluded_is_terminal():
    assert resolve_item(_item(source_refs=[SourceRef(type="code")], excluded=True)) == EXCLUDED
