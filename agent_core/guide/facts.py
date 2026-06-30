"""Extractor output contracts — the facts the three ingestion branches emit.

The branches (source / OpenAPI / runtime) do NOT emit KB directly; they emit these
neutral facts, which InventoryNormalizer merges into one UIInventory. Defining the
contracts here lets the whole downstream pipeline run on sample facts while the actual
extractors (ts-morph / react-docgen / swagger-parser / Playwright — Node + a running
app) are wired later behind these same shapes.

Provenance is first-class: every fact carries a SourceRef so a card can be traced back
and a UI-diff can re-find what to rebuild (ROADMAP M2.2/M2.3).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SourceRef:
    """Where a fact came from. ``type`` selects which fields are meaningful:
    code -> file/symbol; runtime -> scan_run/role/state; openapi -> operation_id;
    i18n -> i18n_key; doc -> file."""

    type: str                       # code | runtime | openapi | i18n | doc
    file: str = ""
    symbol: str = ""
    operation_id: str = ""
    scan_run: str = ""
    role: str = ""
    state: str = ""
    i18n_key: str = ""


# ---- source branch (ts-morph / react-docgen / forms / i18n) ----
@dataclass
class RouteFact:
    route_pattern: str              # e.g. /issues/{issueId} (templated)
    page_component: str
    deeplink: str = ""
    menu_path: list[str] = field(default_factory=list)
    required_roles: list[str] = field(default_factory=list)
    feature_flags: list[str] = field(default_factory=list)
    deprecated: bool = False
    source_ref: SourceRef = field(default_factory=lambda: SourceRef(type="code"))


@dataclass
class ElementFact:
    page_component: str
    element_kind: str               # button | link | tab | heading | label | tooltip | help | dialog | table_column
    text: str = ""                  # rendered/i18n label
    i18n_key: str | None = None
    aria: str = ""
    testid: str = ""
    state: str = "default"          # UI state this element belongs to
    deprecated: bool = False
    source_ref: SourceRef = field(default_factory=lambda: SourceRef(type="code"))


@dataclass
class FormFieldFact:
    page_component: str
    field_name: str
    label: str = ""
    required: bool = False
    input_type: str = "text"
    constraints: dict = field(default_factory=dict)   # min/max/regex
    enum: list[str] = field(default_factory=list)
    help: str = ""
    submit_target: str = ""         # operation_id / url pattern
    source_ref: SourceRef = field(default_factory=lambda: SourceRef(type="code"))


@dataclass
class TransitionFact:
    """An EVIDENCED UI transition. How-to steps may be built only from these (source
    transition, e2e step, runtime safe-scan step, or existing help copy)."""

    page_component: str
    from_state: str
    action: str                     # e.g. "click 'SLA risk only'"
    to_state: str
    origin: str = "source"          # source | e2e | runtime | help
    source_ref: SourceRef = field(default_factory=lambda: SourceRef(type="code"))


@dataclass
class DeadCodeSignal:
    """Knip et al. — ADVISORY only. Never excludes on its own (ROADMAP/Guide §11)."""

    page_component: str
    symbol: str = ""
    reason: str = ""                # unused_export | orphan_file | unresolved_import | deprecated_annotation
    source_ref: SourceRef = field(default_factory=lambda: SourceRef(type="code"))


# ---- OpenAPI branch (swagger-parser) ----
@dataclass
class ApiFact:
    operation_id: str
    method: str = "get"
    path: str = ""
    enums: dict = field(default_factory=dict)        # field -> [values]
    constraints: dict = field(default_factory=dict)
    required_scope: str = ""
    deprecated: bool = False
    source_ref: SourceRef = field(default_factory=lambda: SourceRef(type="openapi"))


# ---- runtime branch (Playwright, per role, safe shallow) ----
@dataclass
class RuntimeObservation:
    """One UI state reached by one role. Captures structure only — never response
    bodies, tokens, or live business values (Guide §9)."""

    role: str
    route_pattern: str
    state: str = "default"
    reached_testids: list[str] = field(default_factory=list)
    reached_aria: list[str] = field(default_factory=list)
    network: list[dict] = field(default_factory=list)   # [{method, path, status}]
    screenshot_ref: str = ""
    scan_run: str = ""


@dataclass
class SourceFacts:
    routes: list[RouteFact] = field(default_factory=list)
    elements: list[ElementFact] = field(default_factory=list)
    form_fields: list[FormFieldFact] = field(default_factory=list)
    transitions: list[TransitionFact] = field(default_factory=list)
    dead_code: list[DeadCodeSignal] = field(default_factory=list)


@dataclass
class ApiFacts:
    operations: list[ApiFact] = field(default_factory=list)


@dataclass
class RuntimeFacts:
    observations: list[RuntimeObservation] = field(default_factory=list)
