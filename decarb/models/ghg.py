"""GHG inventory model (GHG Protocol Scope 1 / 2 / 3).

Scope 2 is reported with BOTH methods, per the GHG Protocol Scope 2 Guidance:
  - location-based : grid average carbon intensity applied to all grid import.
  - market-based   : reflects contractual instruments (PPA / RECs); procured
                     kWh count as ~zero, the remainder at a residual-mix factor.

Every number here is produced by `decarb.engineering.carbon` from inputs and
factors — never estimated by an LLM.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class EmissionLine(BaseModel):
    """One auditable line of the ledger: value = activity x factor."""

    scope: str                 # "1", "2_location", "2_market", "3"
    source: str                # human label, e.g. "Grid electricity import"
    activity_kwh: float = 0.0  # activity data (kWh) where applicable
    factor_kgco2e_per_kwh: float = 0.0
    tco2e: float = 0.0
    note: str = ""


class GHGInventory(BaseModel):
    """Annual greenhouse-gas inventory for a single site state, in tCO2e/yr."""

    scope1_tco2e: float = 0.0
    scope2_location_tco2e: float = 0.0
    scope2_market_tco2e: float = 0.0
    scope3_tco2e: float = 0.0

    # Audit trail: the lines that sum to the scope totals above.
    lines: list[EmissionLine] = Field(default_factory=list)

    @property
    def total_location_based(self) -> float:
        """S1 + S2(location) + S3."""
        return self.scope1_tco2e + self.scope2_location_tco2e + self.scope3_tco2e

    @property
    def total_market_based(self) -> float:
        """S1 + S2(market) + S3."""
        return self.scope1_tco2e + self.scope2_market_tco2e + self.scope3_tco2e

    @property
    def operational_market(self) -> float:
        """S1 + S2(market) — the figure a net-zero *operational* target drives to 0."""
        return self.scope1_tco2e + self.scope2_market_tco2e

    @property
    def operational_location(self) -> float:
        """S1 + S2(location)."""
        return self.scope1_tco2e + self.scope2_location_tco2e
