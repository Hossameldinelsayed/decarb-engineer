"""Site profile data models (the inputs to the decarbonization engine).

Units convention used throughout the package:
  - energy            : kWh per year
  - emission factor   : kgCO2e per kWh
  - carbon intensity  : kgCO2e per kWh (grid)
  - emissions output  : tCO2e per year (1 t = 1000 kg)
  - money             : currency units (treat as USD in the demo)
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class FuelType(str, Enum):
    """Fossil fuels we recognise for Scope 1 accounting."""

    NATURAL_GAS = "natural_gas"
    DIESEL = "diesel"
    LPG = "lpg"
    FUEL_OIL = "fuel_oil"
    PETROL = "petrol"


class ElectrificationMethod(str, Enum):
    """How a fossil end-use can be converted to an electric load."""

    HEAT_PUMP = "heat_pump"          # space/water heating -> heat pump (uses COP)
    RESISTIVE = "resistive"          # direct electric resistance heating (COP = 1)
    GRID_TIE = "grid_tie"            # on-site genset -> grid supply
    EV_FLEET = "ev_fleet"            # combustion fleet -> electric vehicles


class EndUseBreakdown(BaseModel):
    """Share of the building's *electricity* demand by end use.

    Used by efficiency measures to target a slice of load (e.g. lighting only).
    Shares must sum to ~1.0.
    """

    hvac: float = Field(0.45, ge=0, le=1)
    lighting: float = Field(0.20, ge=0, le=1)
    plug_loads: float = Field(0.25, ge=0, le=1)
    other: float = Field(0.10, ge=0, le=1)

    @model_validator(mode="after")
    def _shares_sum_to_one(self) -> "EndUseBreakdown":
        total = self.hvac + self.lighting + self.plug_loads + self.other
        if abs(total - 1.0) > 0.02:
            raise ValueError(f"End-use shares must sum to 1.0 (got {total:.3f})")
        return self

    def share(self, name: str) -> float:
        return {
            "hvac": self.hvac,
            "lighting": self.lighting,
            "plug_loads": self.plug_loads,
            "other": self.other,
        }[name]


class ElectrificationOption(BaseModel):
    """Parameters describing how a fossil end-use would be electrified."""

    method: ElectrificationMethod
    # Coefficient of performance for heat pumps (useful heat out / electricity in).
    cop: float = Field(3.2, gt=0)
    # Efficiency of the *existing* fossil device at delivering useful output.
    #   - boiler thermal efficiency for heating
    #   - electrical efficiency for a genset (fuel kWh -> electrical kWh)
    incumbent_efficiency: float = Field(0.88, gt=0, le=1)


class FossilEndUse(BaseModel):
    """A combustion end-use contributing to Scope 1 emissions."""

    name: str
    fuel_type: FuelType
    annual_fuel_kwh: float = Field(..., ge=0, description="Fuel energy content per year (kWh thermal).")
    # Scope 1 emission factor (kgCO2e per kWh of fuel). If omitted, a default
    # for the fuel type is applied by the carbon engine.
    emission_factor_kgco2e_per_kwh: Optional[float] = Field(None, ge=0)
    electrifiable: bool = True
    electrification: Optional[ElectrificationOption] = None


class GridProfile(BaseModel):
    """Grid electricity carbon intensity (representative monthly profile for MVP)."""

    # 12 monthly average intensities, kgCO2e/kWh (Jan..Dec).
    monthly_intensity_kgco2e_per_kwh: list[float] = Field(..., min_length=12, max_length=12)
    # Residual-mix factor used for *market-based* Scope 2 on un-procured grid kWh.
    # Defaults to the annual average if not supplied (see carbon engine).
    market_residual_factor_kgco2e_per_kwh: Optional[float] = Field(None, ge=0)

    @field_validator("monthly_intensity_kgco2e_per_kwh")
    @classmethod
    def _non_negative(cls, v: list[float]) -> list[float]:
        if any(x < 0 for x in v):
            raise ValueError("Carbon intensities must be non-negative.")
        return v

    @property
    def annual_average(self) -> float:
        return sum(self.monthly_intensity_kgco2e_per_kwh) / 12.0


class Tariff(BaseModel):
    electricity_price_per_kwh: float = Field(0.15, ge=0)
    fuel_price_per_kwh: float = Field(0.06, ge=0)


class Constraints(BaseModel):
    """Operational / comfort constraints the roadmap must respect."""

    # Hard cap on annual grid import (kWh). None = no limit.
    max_grid_import_kwh: Optional[float] = None
    # Minimum acceptable PV self-consumption ratio (avoid massive export with no value).
    # Informational for the MVP; surfaced as a flag, not a hard reject.
    min_pv_self_consumption: float = Field(0.0, ge=0, le=1)
    # Comfort note carried through to the expert gate.
    comfort_note: str = ""


class SiteProfile(BaseModel):
    """Everything the engine needs about a site to design a roadmap."""

    name: str
    location: str = ""
    floor_area_m2: float = Field(..., gt=0)

    annual_electricity_kwh: float = Field(..., ge=0)
    end_use_breakdown: EndUseBreakdown = Field(default_factory=EndUseBreakdown)
    fossil_end_uses: list[FossilEndUse] = Field(default_factory=list)

    grid: GridProfile
    tariff: Tariff = Field(default_factory=Tariff)

    roof_area_m2: float = Field(0.0, ge=0, description="Usable roof area for PV.")

    # Existing green procurement covering this fraction of grid import (market-based).
    existing_green_fraction: float = Field(0.0, ge=0, le=1)

    # Scope 3 is a manual input for the MVP (upstream + downstream, tCO2e/yr).
    scope3_tco2e: float = Field(0.0, ge=0)

    # Planning horizon and ambition.
    base_year: int = 2025
    target_year: int = 2035
    budget_capex: float = Field(..., ge=0, description="Total capex available across the horizon.")

    constraints: Constraints = Field(default_factory=Constraints)

    @property
    def horizon_years(self) -> int:
        return max(1, self.target_year - self.base_year)
