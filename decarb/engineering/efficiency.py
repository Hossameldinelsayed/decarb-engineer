"""Reduce pillar — efficiency measures (deterministic).

Simple end-use-share model: an efficiency measure targets a slice of the
building's *current* electricity demand (e.g. lighting) and cuts it by a
fraction. Savings reduce grid import -> lower Scope 2.

TODO(SE): replace with IES calibrated building energy simulation.
"""

from __future__ import annotations

from ..models.measure import ActionType, MeasureProposal
from ..models.site import SiteProfile
from .effects import MeasureEffect
from .factors import EFFICIENCY_CAPEX_PER_KWH_SAVED, MAX_EFFICIENCY_REDUCTION
from .state import SiteState

# Which end-use share each action type targets.
_ACTION_TO_END_USE: dict[ActionType, str] = {
    ActionType.LIGHTING_RETROFIT: "lighting",
    ActionType.HVAC_UPGRADE: "hvac",
    ActionType.BMS_CONTROLS: "hvac",         # controls mainly trim HVAC
    ActionType.ENVELOPE: "hvac",             # envelope reduces heating/cooling load
    ActionType.PLUG_LOAD_MGMT: "plug_loads",
}


def simulate(site: SiteProfile, state: SiteState,
             proposal: MeasureProposal) -> MeasureEffect:
    """Estimate electricity saved by an efficiency measure on the current state."""
    action = proposal.action_type
    end_use = _ACTION_TO_END_USE.get(action, "other")
    share = site.end_use_breakdown.share(end_use)

    reduction = float(proposal.params.get("reduction", 0.0))
    flags: list[str] = []
    if reduction > MAX_EFFICIENCY_REDUCTION:
        flags.append(
            f"Proposed reduction {reduction:.0%} capped to "
            f"{MAX_EFFICIENCY_REDUCTION:.0%} (feasibility)."
        )
        reduction = MAX_EFFICIENCY_REDUCTION
    reduction = max(0.0, reduction)

    # Savings apply to the share of the CURRENT demand (so a reduce measure
    # scored after electrification sees the larger load — pillars are coupled).
    targeted_kwh = state.electricity_demand_kwh * share
    saved_kwh = targeted_kwh * reduction

    capex_rate = EFFICIENCY_CAPEX_PER_KWH_SAVED.get(action.value, 1.0)
    capex = saved_kwh * capex_rate
    # Energy bill savings (opex reduction shown as a negative delta).
    opex_delta = -saved_kwh * site.tariff.electricity_price_per_kwh

    return MeasureEffect(
        electricity_kwh_delta=-saved_kwh,
        capex=capex,
        annual_opex_delta=opex_delta,
        scopes_affected=["2_location", "2_market"],
        assumptions=[
            f"{end_use} = {share:.0%} of current electricity demand "
            f"({targeted_kwh:,.0f} kWh).",
            f"Reduction {reduction:.0%} -> {saved_kwh:,.0f} kWh/yr saved.",
            f"Capex {capex_rate:.2f} $/kWh-saved -> ${capex:,.0f}.",
        ],
        flags=flags,
    )
