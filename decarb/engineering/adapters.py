"""Adapter interfaces for the proprietary Schneider Electric engineering tools.

The MVP ships a transparent *simplified* model behind each interface (the other
modules in `decarb.engineering`). In production, each Protocol would be backed
by the real tool. These are deliberately thin: they document the seam, they do
NOT reimplement the proprietary algorithms.

Mapping:
  BuildingEnergyAdapter   -> IES (building energy / efficiency simulation)
  ProcessSimAdapter       -> AVEVA Process Simulation (process electrification)
  ElectricalSimAdapter    -> ETAP (electrical network / PV interconnection)
  DispatchAdapter         -> EcoStruxure Microgrid Advisor (PV+battery dispatch)
  CarbonAccountingAdapter -> EcoStruxure Resource Advisor (GHG ledger)
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class BuildingEnergyAdapter(Protocol):
    """Estimate electricity saved by an efficiency measure.

    TODO(SE): replace the simplified end-use-share model with IES building
    energy simulation (calibrated EnergyPlus-class model).
    """

    def estimate_savings_kwh(self, baseline_kwh: float, end_use_share: float,
                             reduction_fraction: float) -> float: ...


@runtime_checkable
class ProcessSimAdapter(Protocol):
    """Convert a fossil end-use into an equivalent electric load.

    TODO(SE): replace with AVEVA Process Simulation for process heat / steam
    electrification and detailed heat-pump performance maps.
    """

    def electric_load_kwh(self, fuel_kwh: float, method: str,
                          cop: float, incumbent_efficiency: float) -> float: ...


@runtime_checkable
class ElectricalSimAdapter(Protocol):
    """Size on-site generation and check interconnection limits.

    TODO(SE): replace with ETAP for load-flow, hosting-capacity and protection
    studies on the PV/battery interconnection.
    """

    def pv_generation_kwh(self, kwp: float, specific_yield: float) -> float: ...


@runtime_checkable
class DispatchAdapter(Protocol):
    """Estimate PV self-consumption given load, PV and storage.

    TODO(SE): replace with EcoStruxure Microgrid Advisor for hourly dispatch
    optimisation instead of the annual self-consumption heuristic.
    """

    def self_consumption_kwh(self, pv_generation_kwh: float, demand_kwh: float,
                             battery_kwh: float) -> float: ...


@runtime_checkable
class CarbonAccountingAdapter(Protocol):
    """Build the GHG ledger for a site state.

    TODO(SE): replace with EcoStruxure Resource Advisor for audited Scope 1/2/3
    accounting with supplier-specific and residual-mix factors.
    """

    def build_inventory(self, state) -> object: ...  # returns GHGInventory
