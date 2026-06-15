"""Replace pillar — clean the remaining electricity (PV / battery / procurement).

  rooftop_pv        : size kWp from roof area or explicit kWp; generation cuts
                      grid import (Scope 2 location + market).
  battery_storage   : lifts PV self-consumption (handled in carbon.py); here we
                      just register the kWh and capex.
  green_procurement : PPA/REC covering a fraction of remaining grid import; cuts
                      market-based Scope 2 only (location-based is unchanged).

TODO(SE): PV interconnection sizing -> ETAP; dispatch -> Microgrid Advisor.
"""

from __future__ import annotations

from ..models.measure import ActionType, MeasureProposal
from ..models.site import SiteProfile
from .carbon import pv_self_consumption_kwh
from .effects import MeasureEffect
from .factors import (
    BATTERY_CAPEX_PER_KWH,
    PPA_CAPEX_PER_KWH,
    PPA_OPEX_PREMIUM_PER_KWH,
    PV_CAPEX_PER_KWP,
    PV_KWP_PER_M2,
    PV_SPECIFIC_YIELD_KWH_PER_KWP,
)
from .state import SiteState


def _max_kwp_from_roof(site: SiteProfile, state: SiteState) -> float:
    installed = state.pv_kwp
    roof_cap = site.roof_area_m2 * PV_KWP_PER_M2
    return max(0.0, roof_cap - installed)


def _simulate_pv(site: SiteProfile, state: SiteState,
                 proposal: MeasureProposal) -> MeasureEffect:
    headroom_kwp = _max_kwp_from_roof(site, state)
    flags: list[str] = []

    if "kwp" in proposal.params:
        kwp = float(proposal.params["kwp"])
    else:
        frac = float(proposal.params.get("roof_fraction", 1.0))
        roof_cap_total = site.roof_area_m2 * PV_KWP_PER_M2
        kwp = roof_cap_total * max(0.0, min(1.0, frac))

    if kwp > headroom_kwp:
        flags.append(
            f"Requested {kwp:,.0f} kWp exceeds roof headroom; capped to "
            f"{headroom_kwp:,.0f} kWp."
        )
        kwp = headroom_kwp

    if kwp <= 0:
        return MeasureEffect(flags=["No roof headroom for additional PV."],
                             assumptions=["No-op PV."])

    generation = kwp * PV_SPECIFIC_YIELD_KWH_PER_KWP
    capex = kwp * PV_CAPEX_PER_KWP

    # Marginal self-consumption (how much of this PV actually displaces import).
    sc_before = pv_self_consumption_kwh(state.pv_generation_kwh,
                                        state.electricity_demand_kwh,
                                        state.battery_kwh)
    sc_after = pv_self_consumption_kwh(state.pv_generation_kwh + generation,
                                       state.electricity_demand_kwh,
                                       state.battery_kwh)
    marginal_self = sc_after - sc_before
    if generation > 0 and marginal_self / generation < 0.5:
        flags.append(
            f"Only {marginal_self / generation:.0%} of this PV is self-consumed "
            "(rest exported); consider storage or procurement instead."
        )

    return MeasureEffect(
        pv_kwp=kwp,
        pv_generation_kwh=generation,
        capex=capex,
        annual_opex_delta=-marginal_self * site.tariff.electricity_price_per_kwh,
        scopes_affected=["2_location", "2_market"],
        assumptions=[
            f"{kwp:,.0f} kWp x {PV_SPECIFIC_YIELD_KWH_PER_KWP:,.0f} kWh/kWp "
            f"= {generation:,.0f} kWh/yr generation.",
            f"~{marginal_self:,.0f} kWh/yr self-consumed (displaces grid import).",
            f"Capex {PV_CAPEX_PER_KWP:,.0f} $/kWp -> ${capex:,.0f}.",
        ],
        flags=flags,
    )


def _simulate_battery(site: SiteProfile, state: SiteState,
                      proposal: MeasureProposal) -> MeasureEffect:
    battery_kwh = float(proposal.params.get("battery_kwh", 0.0))
    if battery_kwh <= 0:
        return MeasureEffect(flags=["No battery capacity specified."],
                             assumptions=["No-op battery."])

    capex = battery_kwh * BATTERY_CAPEX_PER_KWH
    sc_before = pv_self_consumption_kwh(state.pv_generation_kwh,
                                        state.electricity_demand_kwh,
                                        state.battery_kwh)
    sc_after = pv_self_consumption_kwh(state.pv_generation_kwh,
                                       state.electricity_demand_kwh,
                                       state.battery_kwh + battery_kwh)
    extra_self = sc_after - sc_before
    flags: list[str] = []
    if extra_self <= 1.0:
        flags.append("Battery adds little self-consumption (insufficient PV surplus).")

    return MeasureEffect(
        battery_kwh=battery_kwh,
        capex=capex,
        annual_opex_delta=-extra_self * site.tariff.electricity_price_per_kwh,
        scopes_affected=["2_location", "2_market"],
        assumptions=[
            f"{battery_kwh:,.0f} kWh battery -> +{extra_self:,.0f} kWh/yr "
            "PV self-consumption.",
            f"Capex {BATTERY_CAPEX_PER_KWH:,.0f} $/kWh -> ${capex:,.0f}.",
        ],
        flags=flags,
    )


def _simulate_procurement(site: SiteProfile, state: SiteState,
                          proposal: MeasureProposal) -> MeasureEffect:
    # Remaining grid import after current PV self-consumption.
    sc = pv_self_consumption_kwh(state.pv_generation_kwh,
                                 state.electricity_demand_kwh, state.battery_kwh)
    grid_import = max(0.0, state.electricity_demand_kwh - sc)
    already = state.ppa_rec_kwh
    uncovered = max(0.0, grid_import - already)

    frac = float(proposal.params.get("coverage_fraction", 0.0))
    frac = max(0.0, min(1.0, frac))
    new_kwh = uncovered * frac

    capex = new_kwh * PPA_CAPEX_PER_KWH
    opex = new_kwh * PPA_OPEX_PREMIUM_PER_KWH

    return MeasureEffect(
        ppa_rec_kwh=new_kwh,
        capex=capex,
        annual_opex_delta=opex,
        scopes_affected=["2_market"],
        assumptions=[
            f"Cover {frac:.0%} of {uncovered:,.0f} kWh uncovered grid import "
            f"= {new_kwh:,.0f} kWh/yr via PPA/REC.",
            "Affects MARKET-based Scope 2 only; location-based unchanged.",
        ],
    )


def simulate(site: SiteProfile, state: SiteState,
             proposal: MeasureProposal) -> MeasureEffect:
    if proposal.action_type == ActionType.ROOFTOP_PV:
        return _simulate_pv(site, state, proposal)
    if proposal.action_type == ActionType.BATTERY_STORAGE:
        return _simulate_battery(site, state, proposal)
    if proposal.action_type == ActionType.GREEN_PROCUREMENT:
        return _simulate_procurement(site, state, proposal)
    return MeasureEffect(flags=[f"Unsupported replace action {proposal.action_type}."])
