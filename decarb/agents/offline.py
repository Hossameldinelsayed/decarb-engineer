"""Offline (no-LLM) proposal generators, driven by the Schneider catalog.

These let the whole pipeline run end-to-end with ZERO API key. They turn catalog
solutions into proposed *intents* per pillar; the deterministic engineering layer
still computes every kWh / EUR / tCO2e. Reduce is the priority pillar, so all
applicable Schneider efficiency solutions are proposed.
"""

from __future__ import annotations

from ..catalog import load_catalog
from ..models.measure import ActionType, MeasureProposal, Pillar
from ..models.site import SiteProfile

SOURCE = "offline"


def reduce_proposals(site: SiteProfile) -> list[MeasureProposal]:
    """One proposal per applicable Schneider efficiency solution."""
    catalog = load_catalog()
    eub = site.end_use_breakdown
    out: list[MeasureProposal] = []
    for sol in catalog.reduce:
        # Only propose if at least one targeted end-use carries load.
        if not any(eub.share(u) > 0 for u in sol.target_end_uses):
            continue
        out.append(MeasureProposal(
            pillar=Pillar.REDUCE,
            action_type=ActionType.EFFICIENCY_SOLUTION,
            name=sol.name,
            rationale=sol.note,
            params={"solution_id": sol.id, "exclusive_group": sol.exclusive_group},
            source=SOURCE,
        ))
    return out


def replace_proposals(site: SiteProfile) -> list[MeasureProposal]:
    catalog = load_catalog()
    out: list[MeasureProposal] = []
    for sol in catalog.replace:
        # Skip PV/battery when there is no roof.
        if sol.action_type in ("rooftop_pv", "battery_storage") and site.roof_area_m2 <= 0:
            continue
        out.append(MeasureProposal(
            pillar=Pillar.REPLACE,
            action_type=ActionType(sol.action_type),
            name=sol.name,
            rationale=sol.note,
            params=dict(sol.params),
            source=SOURCE,
        ))
    return out


def electrify_proposals(site: SiteProfile) -> list[MeasureProposal]:
    catalog = load_catalog()
    out: list[MeasureProposal] = []
    for use in site.fossil_end_uses:
        if not use.electrifiable:
            continue
        # Match the Schneider solution by the end-use's electrification METHOD
        # (diesel can be a genset OR a fleet), falling back to fuel type.
        sol = None
        if use.electrification is not None:
            sol = catalog.electrify_for_method(use.electrification.method.value)
        if sol is None:
            sol = catalog.electrify_for_fuel(use.fuel_type.value)
        name = f"{sol.name} ({use.name})" if sol else f"Electrify: {use.name}"
        product = sol.product if sol else ""
        out.append(MeasureProposal(
            pillar=Pillar.ELECTRIFY,
            action_type=ActionType.ELECTRIFY_END_USE,
            name=name,
            rationale=(sol.note if sol else f"Remove Scope 1 from {use.name}."),
            params={"target": use.name, "product": product},
            source=SOURCE,
        ))
    return out


def all_proposals(site: SiteProfile) -> list[MeasureProposal]:
    return reduce_proposals(site) + electrify_proposals(site) + replace_proposals(site)
