"""Manifest IO: load a manifest file and compute its immutable digest.

(The manifest *shape* lives in ``agent_core.schemas.manifest``; this package is the
loading/digest layer that turns a file into that validated shape.)
"""
from agent_core.manifest.loader import compute_manifest_digest, load_manifest

__all__ = ["load_manifest", "compute_manifest_digest"]
