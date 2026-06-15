"""MeasureEffect — the physical/financial result of simulating one measure.

Produced by the efficiency / electrify / supply modules; consumed by
`simulate.py` to mutate a SiteState and to build a scored `Measure`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MeasureEffect:
    electricity_kwh_delta: float = 0.0   # - = saving, + = added load
    fuel_kwh_delta: float = 0.0          # - = fuel removed
    target_fossil_name: Optional[str] = None  # fossil end-use this measure reduces
    pv_kwp: float = 0.0
    pv_generation_kwh: float = 0.0
    battery_kwh: float = 0.0
    ppa_rec_kwh: float = 0.0
    capex: float = 0.0
    annual_opex_delta: float = 0.0
    scopes_affected: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
