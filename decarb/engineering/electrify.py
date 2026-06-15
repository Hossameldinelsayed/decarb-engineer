"""Electrify pillar — convert a fossil end-use to an electric load.

Removing combustion drives Scope 1 toward 0 but adds electricity demand (which
then raises Scope 2 until the Replace pillar cleans it). The new electric load
depends on the conversion method:

  heat_pump : electric = useful_heat / COP, useful_heat = fuel x incumbent_eff
  resistive : electric = useful_heat  (COP = 1)
  grid_tie  : electric = fuel x incumbent_electrical_eff  (genset output)
  ev_fleet  : electric = fuel x incumbent_eff x EV_DRIVETRAIN_GAIN

TODO(SE): replace with AVEVA Process Simulation for process heat / steam.
"""

from __future__ import annotations

from ..models.measure import MeasureProposal
from ..models.site import ElectrificationMethod, ElectrificationOption, FossilEndUse, SiteProfile
from .effects import MeasureEffect
from .factors import (
    ELECTRIC_HEAT_FULL_LOAD_HOURS,
    EV_FLEET_CAPEX_PER_KWH,
    GRID_TIE_CAPEX_PER_KWH,
    HEAT_PUMP_CAPEX_PER_KW_ELECTRIC,
)
from .state import SiteState

# Combustion drivetrains are ~3-4x less efficient than electric; converting the
# same delivered service needs far less final energy. Applied for EV fleets.
EV_DRIVETRAIN_GAIN = 0.30  # electric final energy / fossil final energy


def _electric_kwh(fuel_kwh: float, opt: ElectrificationOption) -> tuple[float, str]:
    method = opt.method
    if method == ElectrificationMethod.HEAT_PUMP:
        useful = fuel_kwh * opt.incumbent_efficiency
        elec = useful / opt.cop
        note = (f"useful heat {useful:,.0f} kWh (boiler eff {opt.incumbent_efficiency:.0%}) "
                f"/ COP {opt.cop:.1f} = {elec:,.0f} kWh electric")
    elif method == ElectrificationMethod.RESISTIVE:
        useful = fuel_kwh * opt.incumbent_efficiency
        elec = useful
        note = f"resistive: useful heat {useful:,.0f} kWh = {elec:,.0f} kWh electric"
    elif method == ElectrificationMethod.GRID_TIE:
        elec = fuel_kwh * opt.incumbent_efficiency
        note = (f"genset output {elec:,.0f} kWh "
                f"(electrical eff {opt.incumbent_efficiency:.0%}) now from grid")
    elif method == ElectrificationMethod.EV_FLEET:
        elec = fuel_kwh * opt.incumbent_efficiency * EV_DRIVETRAIN_GAIN
        note = (f"EV fleet: {elec:,.0f} kWh electric "
                f"(drivetrain gain {EV_DRIVETRAIN_GAIN:.2f})")
    else:  # pragma: no cover - exhaustive enum
        raise ValueError(f"Unknown electrification method: {method}")
    return elec, note


def _default_option(use: FossilEndUse) -> ElectrificationOption:
    if use.electrification is not None:
        return use.electrification
    # Sensible default by fuel: gas/oil/lpg -> heat pump; diesel/petrol -> grid tie.
    if use.fuel_type.value in ("diesel", "petrol"):
        return ElectrificationOption(method=ElectrificationMethod.GRID_TIE,
                                     incumbent_efficiency=0.33)
    return ElectrificationOption(method=ElectrificationMethod.HEAT_PUMP)


def _capex(method: ElectrificationMethod, elec_kwh: float) -> float:
    if method in (ElectrificationMethod.HEAT_PUMP, ElectrificationMethod.RESISTIVE):
        kw_electric = elec_kwh / ELECTRIC_HEAT_FULL_LOAD_HOURS
        return kw_electric * HEAT_PUMP_CAPEX_PER_KW_ELECTRIC
    if method == ElectrificationMethod.EV_FLEET:
        return elec_kwh * EV_FLEET_CAPEX_PER_KWH
    return elec_kwh * GRID_TIE_CAPEX_PER_KWH  # grid_tie


def simulate(site: SiteProfile, state: SiteState,
             proposal: MeasureProposal) -> MeasureEffect:
    """Electrify the fossil end-use named in proposal.params['target']."""
    target = proposal.params.get("target")
    use_state = state.find_fossil(target) if target else None
    if use_state is None or use_state.fuel_kwh <= 0:
        return MeasureEffect(
            flags=[f"Electrify target '{target}' not found or already removed."],
            assumptions=["No-op: nothing to electrify."],
        )

    # Recover the option from the original site definition (or a sensible default).
    site_use = next((u for u in site.fossil_end_uses if u.name == target), None)
    opt = _default_option(site_use) if site_use else ElectrificationOption(
        method=ElectrificationMethod.HEAT_PUMP)

    if site_use is not None and not site_use.electrifiable:
        return MeasureEffect(
            flags=[f"'{target}' is flagged not electrifiable."],
            assumptions=["No-op: end-use not electrifiable."],
        )

    fuel_kwh = use_state.fuel_kwh
    elec_kwh, note = _electric_kwh(fuel_kwh, opt)
    capex = _capex(opt.method, elec_kwh)

    # Opex: lose fuel cost, gain electricity cost.
    opex_delta = (elec_kwh * site.tariff.electricity_price_per_kwh
                  - fuel_kwh * site.tariff.fuel_price_per_kwh)

    return MeasureEffect(
        extra_kwh_delta=+elec_kwh,
        fuel_kwh_delta=-fuel_kwh,
        target_fossil_name=target,
        capex=capex,
        annual_opex_delta=opex_delta,
        scopes_affected=["1", "2_location", "2_market"],
        assumptions=[
            f"Remove {fuel_kwh:,.0f} kWh/yr of {use_state.fuel_type} "
            f"(Scope 1 -{fuel_kwh * use_state.emission_factor / 1000:,.1f} tCO2e).",
            f"New electric load: {note}.",
            f"Capex (~${capex:,.0f}) via {opt.method.value} model.",
        ],
    )
