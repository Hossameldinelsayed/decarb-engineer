"""Measure models.

Two stages, reflecting the proposer/computer split:

  MeasureProposal  -- what an LLM agent (or the offline fallback) PROPOSES.
                      Intent + knobs only; NO emissions/energy numbers.
  Measure          -- a proposal AFTER the deterministic engineering layer has
                      SIMULATED it: computed kWh / tCO2e / capex + an audit trail.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class Pillar(str, Enum):
    REDUCE = "reduce"        # efficiency: less energy demand
    ELECTRIFY = "electrify"  # remove fossil end-uses (Scope 1 -> electric load)
    REPLACE = "replace"      # clean the remaining electricity (PV / battery / PPA)


class ActionType(str, Enum):
    # Reduce — a Schneider efficiency solution from the catalog (params.solution_id)
    EFFICIENCY_SOLUTION = "efficiency_solution"
    # Electrify
    ELECTRIFY_END_USE = "electrify_end_use"
    # Replace
    ROOFTOP_PV = "rooftop_pv"
    BATTERY_STORAGE = "battery_storage"
    GREEN_PROCUREMENT = "green_procurement"   # PPA / REC


class MeasureProposal(BaseModel):
    """An agent's proposed action. The engine computes the physics from `params`."""

    pillar: Pillar
    action_type: ActionType
    name: str
    rationale: str = ""
    # Action-specific knobs the engineering layer interprets. Examples:
    #   lighting_retrofit : {"reduction": 0.55}              (fraction of lighting load cut)
    #   hvac_upgrade      : {"reduction": 0.30}
    #   electrify_end_use : {"target": "Gas space heating"}  (FossilEndUse.name)
    #   rooftop_pv        : {"roof_fraction": 0.8}  or {"kwp": 450}
    #   battery_storage   : {"battery_kwh": 800}
    #   green_procurement : {"coverage_fraction": 0.6}       (of remaining grid import)
    params: dict[str, Any] = Field(default_factory=dict)
    source: str = "agent"     # "agent" (live LLM) | "offline" (canned)


class Measure(BaseModel):
    """A proposal scored by the engineering layer.

    Energy deltas use the sign convention: negative = reduction, positive = added load.
    `tco2e_delta` is the *marginal* annual reduction at the state where it was scored
    (positive = emissions avoided).
    """

    proposal: MeasureProposal

    # Computed by engineering — NOT by the LLM.
    capex: float = 0.0
    annual_opex_delta: float = 0.0          # +cost / -savings per year
    electricity_kwh_delta: float = 0.0      # net change in annual electricity demand
    end_use_deltas: dict[str, float] = Field(default_factory=dict)  # building-load changes
    extra_kwh_delta: float = 0.0            # electrification-added load
    fuel_kwh_delta: float = 0.0             # change in annual fossil fuel use
    pv_kwp: float = 0.0
    pv_generation_kwh: float = 0.0
    battery_kwh: float = 0.0
    ppa_rec_kwh: float = 0.0

    tco2e_delta: float = 0.0                # marginal annual emissions avoided
    scopes_affected: list[str] = Field(default_factory=list)

    assumptions: list[str] = Field(default_factory=list)  # audit trail
    flags: list[str] = Field(default_factory=list)        # safety / comfort / feasibility

    # Assigned by the orchestrator when phasing the roadmap.
    year: Optional[int] = None

    @property
    def pillar(self) -> Pillar:
        return self.proposal.pillar

    @property
    def name(self) -> str:
        return self.proposal.name

    @property
    def cost_per_tco2e(self) -> float:
        """Capex per annual tCO2e avoided (lower is better). inf if no abatement."""
        if self.tco2e_delta <= 1e-9:
            return float("inf")
        return self.capex / self.tco2e_delta
