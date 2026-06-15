"""Reduce pillar — Schneider efficiency solutions (the priority pillar).

Each Reduce measure references a solution in the Schneider catalog
(data/schneider_solutions.json). Two things are computed from the BUILDING:
  - carbon: saving_fraction x (current kWh of the targeted end-use bucket(s)),
            converted to tCO2e by the carbon ledger;
  - price : capex_eur_per_m2 x floor_area_m2  -> total price.

Targeting the current bucket value (not a fixed share of the original total)
makes stacked solutions on the same end-use (e.g. several HVAC solutions) abate
and cost accurately, with natural diminishing returns.

TODO(SE): replace the saving fractions with IES calibrated building simulation.
"""

from __future__ import annotations

from ..catalog import ReduceSolution, load_catalog
from ..models.measure import MeasureProposal
from ..models.site import SiteProfile
from .effects import MeasureEffect
from .factors import MAX_EFFICIENCY_REDUCTION
from .state import SiteState


def _solution_for(proposal: MeasureProposal) -> ReduceSolution | None:
    sid = proposal.params.get("solution_id")
    if not sid:
        return None
    return load_catalog().reduce_by_id(sid)


def simulate(site: SiteProfile, state: SiteState,
             proposal: MeasureProposal) -> MeasureEffect:
    """Estimate kWh saved and total price for a Schneider efficiency solution."""
    sol = _solution_for(proposal)
    if sol is None:
        return MeasureEffect(
            flags=[f"No catalog solution for params {proposal.params!r}."],
            assumptions=["No-op: unknown efficiency solution."],
        )

    flags: list[str] = []
    fraction = sol.energy_saving_fraction
    if fraction > MAX_EFFICIENCY_REDUCTION:
        flags.append(f"Saving {fraction:.0%} capped to {MAX_EFFICIENCY_REDUCTION:.0%}.")
        fraction = MAX_EFFICIENCY_REDUCTION
    fraction = max(0.0, fraction)

    # Reduce the CURRENT kWh of each targeted end-use bucket (accurate stacking).
    end_use_deltas: dict[str, float] = {}
    targeted_kwh = 0.0
    for use in sol.target_end_uses:
        current = state.end_use_kwh.get(use, 0.0)
        targeted_kwh += current
        end_use_deltas[use] = -current * fraction
    saved_kwh = targeted_kwh * fraction

    # Price is area-driven: EUR/m2 x floor area = total price.
    capex = sol.capex_eur_per_m2 * site.floor_area_m2
    opex_delta = -saved_kwh * site.tariff.electricity_price_per_kwh

    return MeasureEffect(
        end_use_deltas=end_use_deltas,
        capex=capex,
        annual_opex_delta=opex_delta,
        scopes_affected=sol.scopes_affected,
        assumptions=[
            f"Solution: {sol.product}.",
            f"Targets {', '.join(sol.target_end_uses)} "
            f"({targeted_kwh:,.0f} kWh now) at {fraction:.0%} -> {saved_kwh:,.0f} kWh/yr saved.",
            f"Price {sol.capex_eur_per_m2:,.0f} EUR/m2 x {site.floor_area_m2:,.0f} m2 "
            f"= EUR {capex:,.0f}.",
            f"Basis: {sol.source}",
        ],
        flags=flags,
    )
