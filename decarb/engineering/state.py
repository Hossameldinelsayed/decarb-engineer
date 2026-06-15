"""SiteState — the mutable working state the engine evolves as measures apply.

Derived from a SiteProfile, it holds exactly what the carbon ledger needs. The
orchestrator copies and mutates it as it builds a roadmap, so measures are
scored on the *evolving* state (the pillars are coupled: electrifying adds
load, reducing shrinks it, replacing cleans it).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from ..models.site import SiteProfile
from .factors import FUEL_EMISSION_FACTORS


@dataclass
class FossilUseState:
    name: str
    fuel_type: str
    fuel_kwh: float
    emission_factor: float  # kgCO2e/kWh

    def copy(self) -> "FossilUseState":
        return replace(self)


@dataclass
class SiteState:
    electricity_demand_kwh: float
    fossil_uses: list[FossilUseState] = field(default_factory=list)
    pv_kwp: float = 0.0
    pv_generation_kwh: float = 0.0
    battery_kwh: float = 0.0
    ppa_rec_kwh: float = 0.0           # green-procured kWh (market-based)
    grid_avg_intensity: float = 0.4    # kgCO2e/kWh
    market_residual_factor: float = 0.4
    scope3_tco2e: float = 0.0

    def copy(self) -> "SiteState":
        return SiteState(
            electricity_demand_kwh=self.electricity_demand_kwh,
            fossil_uses=[u.copy() for u in self.fossil_uses],
            pv_kwp=self.pv_kwp,
            pv_generation_kwh=self.pv_generation_kwh,
            battery_kwh=self.battery_kwh,
            ppa_rec_kwh=self.ppa_rec_kwh,
            grid_avg_intensity=self.grid_avg_intensity,
            market_residual_factor=self.market_residual_factor,
            scope3_tco2e=self.scope3_tco2e,
        )

    def find_fossil(self, name: str) -> FossilUseState | None:
        for u in self.fossil_uses:
            if u.name == name:
                return u
        return None


def state_from_site(site: SiteProfile) -> SiteState:
    """Build the baseline working state from a site profile."""
    grid_avg = site.grid.annual_average
    residual = site.grid.market_residual_factor_kgco2e_per_kwh
    if residual is None:
        residual = grid_avg

    fossil = []
    for use in site.fossil_end_uses:
        ef = use.emission_factor_kgco2e_per_kwh
        if ef is None:
            ef = FUEL_EMISSION_FACTORS[use.fuel_type]
        fossil.append(
            FossilUseState(
                name=use.name,
                fuel_type=use.fuel_type.value,
                fuel_kwh=use.annual_fuel_kwh,
                emission_factor=ef,
            )
        )

    # Existing green procurement, expressed as kWh of grid import covered.
    initial_grid_import = max(0.0, site.annual_electricity_kwh)
    ppa = site.existing_green_fraction * initial_grid_import

    return SiteState(
        electricity_demand_kwh=site.annual_electricity_kwh,
        fossil_uses=fossil,
        ppa_rec_kwh=ppa,
        grid_avg_intensity=grid_avg,
        market_residual_factor=residual,
        scope3_tco2e=site.scope3_tco2e,
    )
