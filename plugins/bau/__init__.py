"""BAU plugin — first platform plugin (wiring blueprint).

Wraps bau_center's read tools / domain knowledge / actor-scoped queries / roles as the
four provider interfaces (see providers.py). The provider classes import cleanly; their
methods import BAU's ``core.*`` lazily and run only inside the BAU runtime, where the M1
acceptance (behavior-equivalent on agent_core + the write-consistency fix) is verified
against BAU's own regression suite — not in this repo's CI.
"""
from plugins.bau.providers import BauAuth, BauDataScope, BauKnowledge, BauTools

__all__ = ["BauTools", "BauDataScope", "BauAuth", "BauKnowledge"]
