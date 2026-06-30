"""Demo plugin — self-contained reference implementation of the provider interfaces,
used to validate the runtime walking skeleton end-to-end (see providers.py)."""
from plugins.demo.providers import DemoAuth, DemoDataScope, DemoKnowledge, DemoTools

__all__ = ["DemoTools", "DemoDataScope", "DemoAuth", "DemoKnowledge"]
