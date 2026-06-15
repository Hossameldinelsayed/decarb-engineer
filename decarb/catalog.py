"""Schneider Electric solution catalog (loaded from data/schneider_solutions.json).

The catalog is the bridge between business framing (named Schneider/EcoStruxure
solutions a customer can buy) and the deterministic engine: each Reduce solution
carries an energy_saving_fraction and an EUR/m2 capex, so building floor area
drives BOTH the carbon reduction and the total price. Pricing is illustrative
and adjustable — never an official Schneider quote.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

DEFAULT_CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "schneider_solutions.json"


class ReduceSolution(BaseModel):
    """An efficiency (Reduce) solution priced per m2 of floor area."""

    id: str
    name: str
    product: str = ""
    target_end_uses: list[str] = Field(default_factory=list)
    # Bounds catch catalog-editing typos at load time (e.g. a negative price or a
    # >100% saving) rather than silently clamping them in the engine.
    energy_saving_fraction: float = Field(0.0, ge=0.0, le=1.0)  # of the targeted end-use(s)
    capex_eur_per_m2: float = Field(0.0, ge=0.0)
    exclusive_group: Optional[str] = None    # at most one solution per group
    layer: str = "operate"                   # EcoStruxure layer: onboard | operate | optimize
    scopes_affected: list[str] = Field(default_factory=lambda: ["2_location", "2_market"])
    note: str = ""
    source: str = ""


class SupplySolution(BaseModel):
    """A Replace (clean-supply) solution mapped to a Schneider product + engine action."""

    id: str
    name: str
    product: str = ""
    action_type: str = ""                    # rooftop_pv | battery_storage | green_procurement
    params: dict[str, Any] = Field(default_factory=dict)
    note: str = ""
    source: str = ""


class ElectrifySolution(BaseModel):
    """An Electrify solution mapped to a Schneider product, matched by fuel type."""

    id: str
    name: str
    product: str = ""
    method_match: list[str] = Field(default_factory=list)
    fuel_match: list[str] = Field(default_factory=list)
    note: str = ""
    source: str = ""


class Catalog(BaseModel):
    reduce: list[ReduceSolution] = Field(default_factory=list)
    replace: list[SupplySolution] = Field(default_factory=list)
    electrify: list[ElectrifySolution] = Field(default_factory=list)

    def reduce_by_id(self, sid: str) -> Optional[ReduceSolution]:
        return next((s for s in self.reduce if s.id == sid), None)

    def supply_for_action(self, action_type: str) -> Optional[SupplySolution]:
        return next((s for s in self.replace if s.action_type == action_type), None)

    def electrify_for_fuel(self, fuel_type: str) -> Optional[ElectrifySolution]:
        return next((s for s in self.electrify if fuel_type in s.fuel_match), None)

    def electrify_for_method(self, method: str) -> Optional[ElectrifySolution]:
        return next((s for s in self.electrify if method in s.method_match), None)


def load_catalog(path: str | Path = DEFAULT_CATALOG_PATH) -> Catalog:
    # Read on every call (the JSON is tiny) so edits to the catalog take effect
    # on the next app rerun without needing a process restart.
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return Catalog(
        reduce=[ReduceSolution.model_validate(x) for x in raw.get("reduce", [])],
        replace=[SupplySolution.model_validate(x) for x in raw.get("replace", [])],
        electrify=[ElectrifySolution.model_validate(x) for x in raw.get("electrify", [])],
    )
