"""Decarbonization Engineer — agentic Reduce / Replace / Electrify roadmap designer.

Design principle: LLM agents PROPOSE strategies; the deterministic engineering
layer (`decarb.engineering`) COMPUTES all physics (kWh, tCO2e, cost) from
explicit formulas and factors. Every emissions number is traceable to an input
and an emission/cost factor. A human expert is the mandatory final gate.
"""

__version__ = "0.1.0"
