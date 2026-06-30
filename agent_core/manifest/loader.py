"""Manifest loading + canonical digest (M0 contract surface).

This is the IO / identity layer for manifests, kept distinct from the *shape*
defined in ``agent_core.schemas.manifest``:

  * ``load_manifest``           — read a YAML/JSON file into a validated ChatbotManifest.
  * ``compute_manifest_digest`` — canonical content hash. The SSE/identity contract
    resolves ``deployment_id`` to an IMMUTABLE ``manifest_digest`` (clients never pick
    the running version); this is that digest. Canonical = key-sorted JSON, so two
    logically-equal manifests hash equally regardless of field order (reuses BAU's
    ``_payload_hash`` sort_keys discipline).

The richer M1 loader (``deployment_id -> digest -> per-actor graph build``) layers on
top of these primitives; it does not replace them.
"""
from __future__ import annotations

import hashlib
import json
import pathlib

import yaml

from agent_core.schemas.manifest import ChatbotManifest


def load_manifest(path: str | pathlib.Path) -> ChatbotManifest:
    """Load and validate a manifest from a YAML or JSON file.

    ``yaml.safe_load`` parses JSON too, so one path handles both formats.
    """
    raw = yaml.safe_load(pathlib.Path(path).read_text(encoding="utf-8"))
    return ChatbotManifest.model_validate(raw)


def compute_manifest_digest(manifest: ChatbotManifest) -> str:
    """Immutable, order-independent digest of a manifest's content.

    Key-sorted compact JSON makes the hash depend only on values, not on field
    ordering, so re-serializing an equal manifest yields an equal digest.
    """
    payload = manifest.model_dump(mode="json", by_alias=True)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
