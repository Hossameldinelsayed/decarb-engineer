"""Roadmap models — the ordered, multi-year output of the orchestrator."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .ghg import GHGInventory
from .measure import Measure


class YearSummary(BaseModel):
    """State of the inventory at the end of a given year."""

    year: int
    capex_this_year: float = 0.0
    cumulative_capex: float = 0.0
    inventory: GHGInventory
    pct_reduction_vs_baseline: float = 0.0   # on operational (S1 + S2 market)
    gap_to_net_zero_tco2e: float = 0.0       # remaining operational emissions


class ParetoPoint(BaseModel):
    """A (cost, abatement) point on the cost/carbon frontier."""

    capex: float
    tco2e_reduction: float          # annual operational tCO2e avoided vs baseline
    measure_count: int


class Roadmap(BaseModel):
    """A complete, scored decarbonization roadmap for a site."""

    site_name: str
    base_year: int
    target_year: int
    generated_with: str = "offline"   # "offline" | "live (claude-...)"

    baseline_inventory: GHGInventory
    final_inventory: GHGInventory

    # Ordered measures actually selected (each carries its assigned `year`).
    measures: list[Measure] = Field(default_factory=list)
    # Year-by-year trajectory.
    yearly: list[YearSummary] = Field(default_factory=list)
    # All scored candidates (selected or not) for transparency.
    candidates: list[Measure] = Field(default_factory=list)
    # Cost/carbon frontier.
    pareto: list[ParetoPoint] = Field(default_factory=list)

    @property
    def total_capex(self) -> float:
        return sum(m.capex for m in self.measures)

    @property
    def operational_reduction_tco2e(self) -> float:
        return (
            self.baseline_inventory.operational_market
            - self.final_inventory.operational_market
        )

    @property
    def pct_to_net_zero(self) -> float:
        base = self.baseline_inventory.operational_market
        if base <= 1e-9:
            return 100.0
        return 100.0 * self.operational_reduction_tco2e / base
