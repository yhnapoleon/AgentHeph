"""Runtime engine — built in M1.

M1 ports the BAU chat runtime onto agent_core: LangGraph ReAct loop, tool
governance (dedup + runaway cap + actor injection + artifact sink), SSE event
mapping with call_id pairing, in-process checkpointer, and the manifest loader
that builds a graph per deployment per actor. Validated by the BAU plugin
(behavior-equivalent) — see design/ROADMAP.md M1.
"""
