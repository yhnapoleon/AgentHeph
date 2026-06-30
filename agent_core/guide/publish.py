"""Immutable KB release. Production reads only a frozen KBRelease, never Studio drafts.

Freeze captures the digests that make a build reproducible + auditable (repo commit,
OpenAPI digest, scan plan, UI-inventory digest, card versions, eval result, reviewer).
``freeze`` refuses to release cards that didn't pass the eval gate.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from agent_core.guide.cards import KnowledgeCard


@dataclass
class KBRelease:
    release_id: str
    deployment_id: str
    cards: list[KnowledgeCard]
    digests: dict = field(default_factory=dict)
    reviewer: str = ""
    created_at: str = ""

    def release_digest(self) -> str:
        card_hashes = sorted(c.content_hash() for c in self.cards)
        return "sha256:" + hashlib.sha256(
            json.dumps(card_hashes, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


class KBPublishError(RuntimeError):
    pass


class KBPublisher:
    @staticmethod
    def freeze(
        deployment_id: str,
        cards: list[KnowledgeCard],
        *,
        eval_passed: bool,
        reviewer: str,
        digests: dict | None = None,
    ) -> KBRelease:
        if not eval_passed:
            raise KBPublishError("cannot freeze a KB that did not pass the eval gate")
        if not reviewer:
            raise KBPublishError("a human reviewer is required to freeze a release")
        return KBRelease(
            release_id=uuid.uuid4().hex,
            deployment_id=deployment_id,
            cards=list(cards),
            digests=dict(digests or {}),
            reviewer=reviewer,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
