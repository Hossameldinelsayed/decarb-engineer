"""Deterministic engineering layer.

No LLM here. Every kWh / tCO2e / $ is computed from explicit formulas and the
factors in `factors.py`. Each module documents the Schneider Electric tool that
would replace it in production (see `adapters.py`).
"""

from .carbon import build_inventory, pv_self_consumption_kwh
from .effects import MeasureEffect
from .simulate import apply_effect_to_state, apply_measure, score_proposal
from .state import SiteState, state_from_site

__all__ = [
    "build_inventory",
    "pv_self_consumption_kwh",
    "MeasureEffect",
    "apply_effect_to_state",
    "apply_measure",
    "score_proposal",
    "SiteState",
    "state_from_site",
]
