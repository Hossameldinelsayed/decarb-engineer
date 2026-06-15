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


def _apply(state: SiteState, *, end_use_deltas: dict[str, float], extra_kwh_delta: float,
           fuel_kwh_delta: float, target_fossil_name: str | None,
           pv_kwp: float, pv_generation_kwh: float, battery_kwh: float,
           ppa_rec_kwh: float) -> SiteState:
    new = state.copy()
    for use, delta in end_use_deltas.items():
        new.end_use_kwh[use] = max(0.0, new.end_use_kwh.get(use, 0.0) + delta)
    new.extra_kwh = max(0.0, new.extra_kwh + extra_kwh_delta)
    if target_fossil_name and fuel_kwh_delta:
        fu = new.find_fossil(target_fossil_name)
        if fu is not None:
            fu.fuel_kwh = max(0.0, fu.fuel_kwh + fuel_kwh_delta)
    new.pv_kwp += pv_kwp
    new.pv_generation_kwh += pv_generation_kwh
    new.battery_kwh += battery_kwh
    new.ppa_rec_kwh += ppa_rec_kwh
    return new


def apply_effect_to_state(state: SiteState, effect: MeasureEffect) -> SiteState:
    """Return a new state with the measure's physical effect applied."""
    return _apply(
        state,
        end_use_deltas=effect.end_use_deltas,
        extra_kwh_delta=effect.extra_kwh_delta,
        fuel_kwh_delta=effect.fuel_kwh_delta,
        target_fossil_name=effect.target_fossil_name,
        pv_kwp=effect.pv_kwp,
        pv_generation_kwh=effect.pv_generation_kwh,
        battery_kwh=effect.battery_kwh,
        ppa_rec_kwh=effect.ppa_rec_kwh,
    )


def apply_measure(state: SiteState, measure: Measure) -> SiteState:
    """Apply an already-scored Measure to a state (used for year-by-year replay)."""
    return _apply(
        state,
        end_use_deltas=measure.end_use_deltas,
        extra_kwh_delta=measure.extra_kwh_delta,
        fuel_kwh_delta=measure.fuel_kwh_delta,
        target_fossil_name=measure.proposal.params.get("target"),
        pv_kwp=measure.pv_kwp,
        pv_generation_kwh=measure.pv_generation_kwh,
        battery_kwh=measure.battery_kwh,
        ppa_rec_kwh=measure.ppa_rec_kwh,
    )


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
        end_use_deltas=dict(effect.end_use_deltas),
        extra_kwh_delta=effect.extra_kwh_delta,
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
