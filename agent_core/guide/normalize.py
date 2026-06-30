"""InventoryNormalizer — merge SourceFacts + ApiFacts + RuntimeFacts into one UIInventory.

Beyond mapping facts to items it: templates dynamic path segments (``/issues/123`` ->
``/issues/{id}``), strips dynamic counts/timestamps from labels, unifies i18n keys,
merges multi-role runtime results onto one item, dedups by identity (unioning
provenance + role visibility), and keeps all source_refs. It assigns NO evidence
status — that is EvidenceResolver's job — and NO domain/capability keys yet (TopicPlanner
does that); items start with ``capability`` from the source where available.
"""
from __future__ import annotations

import re

from agent_core.guide.facts import ApiFacts, RuntimeFacts, SourceFacts
from agent_core.guide.inventory import InventoryItem, UIInventory

_NUM_SEG = re.compile(r"/\d+(?=/|$)")
_UUID_SEG = re.compile(r"/[0-9a-fA-F-]{8,}(?=/|$)")
_COUNT = re.compile(r"\s*\(\s*\d+\s*\)\s*$")          # "Issues (12)" -> "Issues"
_TIMESTAMP = re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}\S*")


def template_path(path: str) -> str:
    path = _UUID_SEG.sub("/{id}", path)
    return _NUM_SEG.sub("/{id}", path)


def _clean_label(text: str) -> str:
    return _TIMESTAMP.sub("", _COUNT.sub("", text or "")).strip()


def _merge_into(index: dict[tuple, InventoryItem], item: InventoryItem) -> None:
    key = item.identity()
    existing = index.get(key)
    if existing is None:
        index[key] = item
        return
    # union provenance + role visibility, keep the richer attrs, sum deprecation signals.
    seen = {(r.type, r.file, r.symbol, r.operation_id, r.scan_run, r.role, r.state)
            for r in existing.source_refs}
    for r in item.source_refs:
        if (r.type, r.file, r.symbol, r.operation_id, r.scan_run, r.role, r.state) not in seen:
            existing.source_refs.append(r)
    for role, reached in item.role_visibility.items():
        existing.role_visibility[role] = existing.role_visibility.get(role, False) or reached
    existing.required_roles = sorted(set(existing.required_roles) | set(item.required_roles))
    existing.api_bindings = sorted(set(existing.api_bindings) | set(item.api_bindings))
    existing.attrs = {**item.attrs, **existing.attrs}
    existing.deprecation_signals += item.deprecation_signals


class InventoryNormalizer:
    def merge(self, source: SourceFacts, api: ApiFacts, runtime: RuntimeFacts) -> UIInventory:
        index: dict[tuple, InventoryItem] = {}
        # component -> route, so every item on a page shares the page's route key (the
        # route is the stable UI-page identity; component name is kept in attrs).
        comp_to_route = {r.page_component: template_path(r.route_pattern) for r in source.routes}

        def page_of(component: str) -> str:
            return comp_to_route.get(component, component)

        for r in source.routes:
            _merge_into(index, InventoryItem(
                kind="page", domain="", capability=r.page_component, page=template_path(r.route_pattern),
                name=template_path(r.route_pattern),
                attrs={"deeplink": r.deeplink, "menu_path": r.menu_path, "component": r.page_component},
                required_roles=list(r.required_roles),
                deprecation_signals=1 if r.deprecated else 0, source_refs=[r.source_ref],
            ))

        for e in source.elements:
            name = e.i18n_key or _clean_label(e.text)
            _merge_into(index, InventoryItem(
                kind="element", domain="", capability=e.page_component, page=page_of(e.page_component),
                name=name,
                attrs={"element_kind": e.element_kind, "text": _clean_label(e.text),
                       "i18n_key": e.i18n_key, "testid": e.testid, "aria": e.aria, "state": e.state},
                deprecation_signals=1 if e.deprecated else 0, source_refs=[e.source_ref],
            ))

        for f in source.form_fields:
            _merge_into(index, InventoryItem(
                kind="form_field", domain="", capability=f.page_component, page=page_of(f.page_component),
                name=f.field_name,
                attrs={"label": _clean_label(f.label), "required": f.required, "input_type": f.input_type,
                       "constraints": f.constraints, "help": _clean_label(f.help)},
                api_bindings=[f.submit_target] if f.submit_target else [],
                source_refs=[f.source_ref],
            ))
            for value in f.enum:
                _merge_into(index, InventoryItem(
                    kind="enum", domain="", capability=f.page_component, page=page_of(f.page_component),
                    name=f"{f.field_name}={value}", attrs={"field": f.field_name, "value": value},
                    source_refs=[f.source_ref],
                ))

        for t in source.transitions:
            _merge_into(index, InventoryItem(
                kind="transition", domain="", capability=t.page_component, page=page_of(t.page_component),
                name=t.action,
                attrs={"from_state": t.from_state, "to_state": t.to_state, "origin": t.origin},
                source_refs=[t.source_ref],
            ))

        for s in source.dead_code:
            # advisory only: bump deprecation signal on matching items, never exclude.
            for it in index.values():
                if it.capability == s.page_component and (not s.symbol or s.symbol in (it.name, it.attrs.get("testid", ""))):
                    it.deprecation_signals += 1

        self._apply_api(index, api)
        self._apply_runtime(index, runtime)
        return UIInventory(items=list(index.values()))

    def _apply_api(self, index: dict[tuple, InventoryItem], api: ApiFacts) -> None:
        by_op = {o.operation_id: o for o in api.operations}
        for it in list(index.values()):
            for op_id in it.api_bindings:
                op = by_op.get(op_id)
                if op is None:
                    continue
                if op.deprecated:
                    it.deprecation_signals += 1
                it.source_refs.append(op.source_ref)
                # enrich enums from the API contract (field -> values)
                for field_name, values in op.enums.items():
                    for value in values:
                        _merge_into(index, InventoryItem(
                            kind="enum", domain="", capability=it.capability, page=it.page,
                            name=f"{field_name}={value}", attrs={"field": field_name, "value": value},
                            api_bindings=[op_id], source_refs=[op.source_ref],
                        ))

    def _apply_runtime(self, index: dict[tuple, InventoryItem], runtime: RuntimeFacts) -> None:
        for obs in runtime.observations:
            route = template_path(obs.route_pattern)
            for it in index.values():
                hit = (
                    (it.kind == "page" and it.page == route)
                    or (it.kind == "element" and it.attrs.get("testid") in obs.reached_testids
                        and it.attrs.get("testid"))
                    or (it.kind == "element" and it.attrs.get("aria") in obs.reached_aria
                        and it.attrs.get("aria"))
                )
                if hit:
                    it.role_visibility[obs.role] = True
                    it.source_refs.append(_runtime_ref(obs))


def _runtime_ref(obs):
    from agent_core.guide.facts import SourceRef

    return SourceRef(type="runtime", scan_run=obs.scan_run, role=obs.role, state=obs.state)
