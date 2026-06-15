"""Reduce agent — proposes Schneider efficiency solutions (the priority pillar).

Live mode lets Claude pick which catalog solutions fit the site; offline mode
proposes all applicable ones. Either way the engineering layer prices each
solution at EUR/m2 x floor area and computes the carbon reduction.
"""

from __future__ import annotations

from ..catalog import load_catalog
from ..models.measure import MeasureProposal, Pillar
from ..models.site import SiteProfile
from . import base, offline

SYSTEM = """You are a Schneider Electric energy-efficiency consultant. Reduce
(efficiency) is the PRIORITY pillar. From the catalog of Schneider solutions
provided, choose the ones that best fit this building. Propose each as
action_type 'efficiency_solution' with params {"solution_id": "<id>"}. Pick at
most ONE solution per building-management system (do not propose both a full BMS
and the small-building alternative). Do NOT estimate kWh, cost or CO2 — the
engineering layer prices each at EUR/m2 and computes savings. Return your
selection via the submit_proposals tool."""


def _catalog_text() -> str:
    lines = ["Available Schneider efficiency solutions (id: name [targets] ~saving):"]
    for s in load_catalog().reduce:
        grp = f" group={s.exclusive_group}" if s.exclusive_group else ""
        lines.append(
            f"- {s.id}: {s.name} [{', '.join(s.target_end_uses)}] "
            f"~{s.energy_saving_fraction:.0%}{grp}"
        )
    return "\n".join(lines)


def _enrich(props: list[MeasureProposal]) -> list[MeasureProposal]:
    """Attach the catalog's exclusive_group / canonical name to live proposals."""
    catalog = load_catalog()
    enriched: list[MeasureProposal] = []
    for p in props:
        sol = catalog.reduce_by_id(p.params.get("solution_id", ""))
        if sol is None:
            continue  # drop hallucinated solution ids
        p.params["exclusive_group"] = sol.exclusive_group
        p.name = sol.name
        enriched.append(p)
    return enriched


def propose(site: SiteProfile, live: bool | None = None) -> list[MeasureProposal]:
    use_live = base.is_live() if live is None else live
    if use_live:
        try:
            user = base.site_summary(site) + "\n\n" + _catalog_text()
            batch = base.call_agent(SYSTEM, user)
            props = [p for p in batch.to_measure_proposals() if p.pillar == Pillar.REDUCE]
            props = _enrich(props)
            if props:
                return props
        except Exception as exc:  # noqa: BLE001 - any failure -> deterministic fallback
            print(f"[reduce_agent] live call failed ({exc}); using offline proposals.")
    return offline.reduce_proposals(site)
