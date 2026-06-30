"""System-prompt assembly: a hard-coded discipline skeleton + manifest-filled slots.

The discipline skeleton is the platform's "scar tissue" — anti-fabrication,
anti-sycophancy, language mirroring, call restraint, the three kinds of "no data",
and stored-vs-general-advice separation. It is **abstracted from BAU's CHAT_SYSTEM**
(which proved these rules through regression) and is deliberately app-agnostic: no
tool names, no domain terms. Plugins never rewrite it — they only fill slots, and a
generated prompt must pass eval before it ships (see ROADMAP §9).

``build_system_prompt`` composes ``<discipline skeleton> + <slots>``. Slots come from
``manifest.prompt.slots`` (e.g. app description, domain card, tool-routing notes),
resolved by the caller from the content store before they reach here.
"""
from __future__ import annotations

from agent_core.schemas.identity import Principal
from agent_core.schemas.manifest import ChatbotManifest

# One source for language + output hygiene, shared by every profile so branches
# can't drift (BAU's SHARED_LANG_RULE lesson).
SHARED_LANG_RULE = (
    "Language & brevity: answer in the user's language (mirror it; do not reply in "
    "English to a non-English question). Keep answers short; prefer compact tables or "
    "id-bearing lists. Never expose internal tool names, raw field names, or raw JSON "
    "in prose."
)

# discipline_profile -> hard-coded skeleton. Add profiles here; never let a plugin
# author free-write one.
DISCIPLINE_PROFILES: dict[str, str] = {
    "strict-internal": """\
You are an assistant for an internal business application. Data you can read is
already scoped to the current user's permissions.

## Grounding (highest priority)
- Answer only from what the tools return. Every id, name, contact, link, step, time,
  and conclusion must trace to a specific field a tool returned this turn. If it does
  not, do not write it — say "not recorded / not found". Prefer a short answer over a
  fluent-but-fabricated one. Placeholder emails/domains count as "no contact".
- Three kinds of "no": (1) a tool returned empty -> "nothing found"; (2) you have no
  tool to read this kind of fact -> "I can't read X", never guess from general
  knowledge; (3) the user asserts a fact -> verify with a tool before agreeing.

## Anti-sycophancy
- The user's premise may be wrong. Verify with a tool when you can; otherwise say
  "you may be right, but I have no source to confirm". Do not change a tool-supported
  conclusion just because the user pushes back — re-check the tool data or state the
  uncertainty. Never invent supporting evidence to please the user.

## Stored vs. general advice (must stay separated)
- First restate what the system actually records. Only then, if useful, in a clearly
  labelled separate section, add general advice marked as "not from the system". Never
  dress general advice up as a stored record. Do not self-compute numbers (thresholds,
  rates, deltas, timezone conversions) — cite the tool's returned field.

## Call restraint
- Don't re-ask the same tool with tweaked params to "be thorough". Different tools
  cover different dimensions; once you can answer, stop and answer.

{lang_rule}
""",
}


def build_system_prompt(
    manifest: ChatbotManifest,
    principal: Principal,
    *,
    resolved_slots: dict[str, str] | None = None,
) -> str:
    """Compose the system prompt for one deployment + actor.

    ``resolved_slots`` are the already-fetched slot contents (domain card, tool-routing
    notes, app description) keyed by slot name; unknown profiles fall back to
    ``strict-internal`` so a bad manifest can never produce a discipline-free prompt.
    """
    profile = manifest.prompt.discipline_profile
    skeleton = DISCIPLINE_PROFILES.get(profile, DISCIPLINE_PROFILES["strict-internal"])
    parts = [skeleton.format(lang_rule=SHARED_LANG_RULE)]

    if manifest.metadata.description:
        parts.append(f"## Application\n{manifest.metadata.description}")

    for name, content in (resolved_slots or {}).items():
        if content:
            parts.append(f"## {name}\n{content}")

    parts.append(f"Current user: {principal.subject} (roles: {', '.join(principal.roles) or 'none'}).")
    return "\n\n".join(parts)
