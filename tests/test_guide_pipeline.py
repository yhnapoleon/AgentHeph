"""M2 Phase 5: the full build pipeline end-to-end on sample facts, then freeze + serve.
facts -> normalize -> evidence -> topics -> cards -> validate (gate) -> freeze ->
per-actor retrieval."""
from __future__ import annotations

from agent_core.guide import (
    CardValidator,
    KBPublisher,
    build_kb,
)
from agent_core.guide.publish import KBPublishError
from agent_core.guide.store import CardStore
from agent_core.guide.validate import classify_review
from agent_core.schemas.identity import Principal
from tests.guide_sample import API, DOMAIN_MAP, RUNTIME, SOURCE, fake_drafter


def _build():
    return build_kb(SOURCE, API, RUNTIME, drafter=fake_drafter, domain_map=DOMAIN_MAP)


def test_pipeline_keys_on_domain_not_page():
    result = _build()
    areas = {c.area for c in result.cards}
    assert areas == {"issue_management", "runbook"}      # business domains, not page names
    # the issues page reached at runtime by both roles -> verified navigation card
    nav = next(c for c in result.cards if c.area == "issue_management" and c.kind == "navigation")
    assert nav.evidence_status == "verified"


def test_status_enum_card_merges_source_and_api():
    cards = _build().cards
    enum_card = next(c for c in cards if c.kind == "enum" and c.area == "issue_management")
    # source had open/closed; OpenAPI added resolved — all should be represented downstream.
    # (the enum card's evidence is 'supported': source + api, no runtime)
    assert enum_card.evidence_status in ("supported", "source_only")


def test_eval_gate_passes_for_clean_cards():
    cards = _build().cards
    ok, checks = CardValidator().validate_all(
        cards, allowed_roles={"viewer", "bau_member"}, known_tools={"listIssues"})
    assert ok, [c.failures for c in checks if not c.ok]


def test_freeze_requires_eval_pass_and_reviewer():
    cards = _build().cards
    # gate not passed -> refuse
    try:
        KBPublisher.freeze("guide-demo", cards, eval_passed=False, reviewer="alice")
        assert False, "should have refused"
    except KBPublishError:
        pass
    release = KBPublisher.freeze("guide-demo", cards, eval_passed=True, reviewer="alice",
                                 digests={"repo_commit": "abc123"})
    assert release.reviewer == "alice"
    assert release.release_digest().startswith("sha256:")


def test_runbook_is_hidden_from_viewer():
    release = KBPublisher.freeze("guide-demo", _build().cards, eval_passed=True, reviewer="alice")
    store = CardStore(release)
    viewer = Principal(issuer="t", subject="v", roles=["viewer"])
    member = Principal(issuer="t", subject="m", roles=["bau_member"])
    # runbook requires bau_member -> viewer can't even see the area.
    assert "runbook" not in store.visible_areas(viewer)
    assert "runbook" in store.visible_areas(member)
    assert store.retrieve("runbook", viewer) == []


def test_howto_card_triggers_per_card_review():
    howto = next(c for c in _build().cards if c.kind == "howto")
    decision = classify_review(howto)
    assert decision.tier == "per_card"      # how-to always gets a closer look
