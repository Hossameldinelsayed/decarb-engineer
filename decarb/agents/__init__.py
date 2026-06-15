"""LLM agent layer (Anthropic SDK) — proposes measures as structured JSON.

Agents PROPOSE intent only; the deterministic engineering layer computes all
physics. Every agent has an offline fallback so the system runs with no API key.
"""

from . import electrify_agent, orchestrator, reduce_agent, replace_agent

__all__ = ["orchestrator", "reduce_agent", "electrify_agent", "replace_agent"]
