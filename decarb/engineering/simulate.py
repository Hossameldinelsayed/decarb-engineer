"""Glue: score a MeasureProposal against a state, and apply a Measure to a state.

This is where "agents propose, engineering computes" is enforced: the marginal
tCO2e of every measure is computed by re-running the carbon ledger before and
after the measure's physical effect — never taken from the proposal.
"""

from __future__ import annotations

from ..models.measure import Measure, MeasureProposal, Pillar
from ..models.site import SiteProfile
from . import efficiency, electrify, supply
from .carbon import build_inventory
from .effects import MeasureEffect
from .state import SiteState


def _simulate_effect(site: SiteProfile, state: SiteState,
                     proposal: MeasureProposal) -> MeasureEffect:
    if proposal.pillar == Pillar.REDUCE:
        return efficiency.simulate(site, state, proposal)
    if proposal.pillar == Pillar.ELECTRIFY:
        return electrify.simulate(site, state, proposal)
    if proposal.pillar == Pillar.REPLACE:
        return supply.simulate(site, state, proposal)
    raise ValueError(f"Unknown pillar: {proposal.pillar}")


def apply_effect_to_state(state: SiteState, effect: MeasureEffect) -> SiteState:
    """Return a new state with the measure's physical effect applied."""
    new = state.copy()
    new.electricity_demand_kwh = max(0.0, new.electricity_demand_kwh
                                     + effect.electricity_kwh_delta)
    if effect.target_fossil_name and effect.fuel_kwh_delta:
        use = new.find_fossil(effect.target_fossil_name)
        if use is not None:
            use.fuel_kwh = max(0.0, use.fuel_kwh + effect.fuel_kwh_delta)
    new.pv_kwp += effect.pv_kwp
    new.pv_generation_kwh += effect.pv_generation_kwh
    new.battery_kwh += effect.battery_kwh
    new.ppa_rec_kwh += effect.ppa_rec_kwh
    return new


def apply_measure(state: SiteState, measure: Measure) -> SiteState:
    """Apply an already-scored Measure to a state (used for year-by-year replay)."""
    effect = MeasureEffect(
        electricity_kwh_delta=measure.electricity_kwh_delta,
        fuel_kwh_delta=measure.fuel_kwh_delta,
        target_fossil_name=measure.proposal.params.get("target"),
        pv_kwp=measure.pv_kwp,
        pv_generation_kwh=measure.pv_generation_kwh,
        battery_kwh=measure.battery_kwh,
        ppa_rec_kwh=measure.ppa_rec_kwh,
    )
    return apply_effect_to_state(state, effect)


def score_proposal(site: SiteProfile, state: SiteState,
                   proposal: MeasureProposal) -> tuple[Measure, SiteState]:
    """Simulate a proposal on `state`. Returns the scored Measure and the
    resulting state (the marginal tCO2e is computed on this state)."""
    effect = _simulate_effect(site, state, proposal)

    inv_before = build_inventory(state)
    new_state = apply_effect_to_state(state, effect)
    inv_after = build_inventory(new_state)

    tco2e_delta = inv_before.operational_market - inv_after.operational_market

    measure = Measure(
        proposal=proposal,
        capex=effect.capex,
        annual_opex_delta=effect.annual_opex_delta,
        electricity_kwh_delta=effect.electricity_kwh_delta,
        fuel_kwh_delta=effect.fuel_kwh_delta,
        pv_kwp=effect.pv_kwp,
        pv_generation_kwh=effect.pv_generation_kwh,
        battery_kwh=effect.battery_kwh,
        ppa_rec_kwh=effect.ppa_rec_kwh,
        tco2e_delta=tco2e_delta,
        scopes_affected=effect.scopes_affected,
        assumptions=effect.assumptions,
        flags=effect.flags,
    )
    return measure, new_state
