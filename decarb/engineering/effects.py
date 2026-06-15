"""MeasureEffect — the physical/financial result of simulating one measure.

Produced by the efficiency / electrify / supply modules; consumed by
`simulate.py` to mutate a SiteState and to build a scored `Measure`.

Energy effects are split so they map onto the per-end-use SiteState:
  - end_use_deltas : changes to building end-use buckets (Reduce; negative)
  - extra_kwh_delta: electrification-added load (Electrify; positive)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MeasureEffect:
    end_use_deltas: dict[str, float] = field(default_factory=dict)  # building loads, - = saving
    extra_kwh_delta: float = 0.0          # electrification-added electric load (+)
    fuel_kwh_delta: float = 0.0           # - = fuel removed
    target_fossil_name: Optional[str] = None
    pv_kwp: float = 0.0
    pv_generation_kwh: float = 0.0
    battery_kwh: float = 0.0
    ppa_rec_kwh: float = 0.0
    capex: float = 0.0
    annual_opex_delta: float = 0.0
    scopes_affected: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)

    @property
    def electricity_kwh_delta(self) -> float:
        """Net change in total electricity demand (for display)."""
        return sum(self.end_use_deltas.values()) + self.extra_kwh_delta
