"""Ingestion extractor interfaces — the three branches that produce facts.

RUNTIME BOUNDARY: the real implementations are **Node + a running app**, not Python:
  * Source branch — ts-morph, react-docgen, i18next-parser, knip (TypeScript AST).
  * OpenAPI branch — swagger-parser (Node) or a Python OpenAPI parser.
  * Runtime branch — Playwright driving the deployed app per role (safe shallow scan).

They are therefore invoked out-of-process (a Node sidecar / CLI) and hand back JSON that
deserializes into the ``facts.py`` contracts. Defining the interfaces here lets the whole
Python pipeline (normalize -> evidence -> cluster -> cards -> validate -> freeze -> serve)
be built and tested against sample facts now, with the extractors slotting in behind
these Protocols later — the same pattern as the BAU plugin boundary.

Safety invariants the runtime extractor MUST honor (Guide §9), enforced at integration:
  * allowed: open route, click nav, switch tab, open/close dialog, hover tooltip,
    side-effect-free filters, paginate;
  * forbidden: submit / Save / Delete / Approve / Send / Upload / pay / change config;
  * never capture: response bodies, Authorization header, cookies/tokens, user input,
    live business values.
"""
from __future__ import annotations

from typing import Protocol

from agent_core.guide.facts import ApiFacts, RuntimeFacts, SourceFacts


class ProjectProfile(Protocol):
    """Detected frontend shape (React version, TS config, router, i18n, form lib, API
    client paths, e2e paths). M2 targets a single React+TS stack; multi-stack is later."""

    framework: str
    router: str
    i18n: str


class SourceExtractor(Protocol):
    """ts-morph + react-docgen + i18next-parser (+ knip signals)."""

    def extract(self, repo_path: str, profile: ProjectProfile) -> SourceFacts: ...


class OpenApiExtractor(Protocol):
    """swagger-parser: validate, resolve $ref, canonicalize, extract operations/enums."""

    def extract(self, spec_path: str) -> ApiFacts: ...


class RuntimeScanner(Protocol):
    """Playwright per-role safe shallow scan. ``scan_plan`` carries the confirmed roles,
    per-role auth profile refs, and seed routes; it is frozen before scanning."""

    def scan(self, base_url: str, scan_plan: dict) -> RuntimeFacts: ...
