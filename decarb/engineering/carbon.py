"""Carbon ledger — turn a SiteState into a GHG inventory (tCO2e/yr).

This is the auditable heart of the engine. Every line is `activity x factor`.

TODO(SE): replace with EcoStruxure Resource Advisor for audited Scope 1/2/3
accounting (supplier-specific factors, residual mix, time-matched Scope 2).
"""

from __future__ import annotations

from ..models.ghg import EmissionLine, GHGInventory
from .factors import (
    BATTERY_CYCLES_PER_YEAR,
    BATTERY_ROUND_TRIP_EFFICIENCY,
    PV_DAYTIME_COINCIDENCE,
)
from .state import SiteState

KG_PER_TONNE = 1000.0


def pv_self_consumption_kwh(pv_generation_kwh: float, demand_kwh: float,
                            battery_kwh: float) -> float:
    """Annual PV self-consumption heuristic (stands in for hourly dispatch).

    Without storage, only the daytime-coincident fraction of PV is used on site.
    A battery shifts surplus into non-coincident hours, bounded by its annual
    throughput and by the remaining (uncovered) demand and surplus.

    TODO(SE): replace with EcoStruxure Microgrid Advisor hourly dispatch.
    """
    if pv_generation_kwh <= 0 or demand_kwh <= 0:
        return 0.0

    base = min(pv_generation_kwh * PV_DAYTIME_COINCIDENCE, demand_kwh)

    surplus = pv_generation_kwh - base          # PV input available to charge
    remaining_demand = demand_kwh - base        # demand not yet met by PV
    battery_throughput = (
        battery_kwh * BATTERY_CYCLES_PER_YEAR * BATTERY_ROUND_TRIP_EFFICIENCY
    )
    # All three bounds are expressed as *delivered* (output) energy: the battery
    # throughput already nets round-trip losses, and the surplus only delivers
    # `surplus * round_trip` to the load after charge/discharge losses. Mixing
    # input-side surplus with output-side bounds would overstate self-consumption.
    deliverable_from_surplus = surplus * BATTERY_ROUND_TRIP_EFFICIENCY
    extra = max(0.0, min(battery_throughput, deliverable_from_surplus, remaining_demand))

    return min(base + extra, pv_generation_kwh, demand_kwh)


def build_inventory(state: SiteState) -> GHGInventory:
    """Compute the full Scope 1/2/3 inventory for a site state."""
    lines: list[EmissionLine] = []

    # --- Scope 1: on-site fuel combustion -----------------------------------
    scope1_kg = 0.0
    for use in state.fossil_uses:
        kg = use.fuel_kwh * use.emission_factor
        scope1_kg += kg
        if use.fuel_kwh > 0:
            lines.append(EmissionLine(
                scope="1",
                source=use.name,
                activity_kwh=use.fuel_kwh,
                factor_kgco2e_per_kwh=use.emission_factor,
                tco2e=kg / KG_PER_TONNE,
                note=f"Fuel: {use.fuel_type}",
            ))

    # --- Electricity: PV self-consumption then grid import ------------------
    pv_self = pv_self_consumption_kwh(
        state.pv_generation_kwh, state.electricity_demand_kwh, state.battery_kwh
    )
    grid_import = max(0.0, state.electricity_demand_kwh - pv_self)

    # Scope 2 location-based: all grid import at the grid average intensity.
    s2_loc_kg = grid_import * state.grid_avg_intensity
    lines.append(EmissionLine(
        scope="2_location",
        source="Grid electricity import (location-based)",
        activity_kwh=grid_import,
        factor_kgco2e_per_kwh=state.grid_avg_intensity,
        tco2e=s2_loc_kg / KG_PER_TONNE,
        note=f"PV self-consumed {pv_self:,.0f} kWh of {state.electricity_demand_kwh:,.0f} demand",
    ))

    # Scope 2 market-based: procured (PPA/REC) kWh ~zero; remainder at residual.
    covered = min(state.ppa_rec_kwh, grid_import)
    uncovered = max(0.0, grid_import - covered)
    s2_mkt_kg = uncovered * state.market_residual_factor
    lines.append(EmissionLine(
        scope="2_market",
        source="Grid electricity import (market-based)",
        activity_kwh=uncovered,
        factor_kgco2e_per_kwh=state.market_residual_factor,
        tco2e=s2_mkt_kg / KG_PER_TONNE,
        note=f"{covered:,.0f} kWh covered by PPA/REC at ~0 gCO2e",
    ))

    # --- Scope 3: manual input for the MVP ----------------------------------
    if state.scope3_tco2e:
        lines.append(EmissionLine(
            scope="3",
            source="Scope 3 (manual upstream + downstream)",
            tco2e=state.scope3_tco2e,
            note="Manual input for MVP; not abated by site measures here.",
        ))

    return GHGInventory(
        scope1_tco2e=scope1_kg / KG_PER_TONNE,
        scope2_location_tco2e=s2_loc_kg / KG_PER_TONNE,
        scope2_market_tco2e=s2_mkt_kg / KG_PER_TONNE,
        scope3_tco2e=state.scope3_tco2e,
        lines=lines,
    )
