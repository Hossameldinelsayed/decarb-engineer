"""Electrify agent — proposes converting fossil end-uses to electric loads."""

from __future__ import annotations

from ..models.measure import MeasureProposal, Pillar
from ..models.site import SiteProfile
from . import base, offline

SYSTEM = """You are an electrification engineer on a decarbonization team.
Propose ONLY 'electrify' measures that remove on-site fossil combustion (Scope 1)
by switching an end-use to electricity. Use action type electrify_end_use with
params {"target": "<exact fossil end-use name from the site>"}. Propose one
measure per electrifiable fossil end-use listed for the site. Do NOT estimate
kWh, cost or CO2 — the engineering layer computes the new electric load.
Return your proposals via the submit_proposals tool."""


def propose(site: SiteProfile, live: bool | None = None) -> list[MeasureProposal]:
    use_live = base.is_live() if live is None else live
    if use_live:
        try:
            batch = base.call_agent(SYSTEM, base.site_summary(site))
            props = [p for p in batch.to_measure_proposals() if p.pillar == Pillar.ELECTRIFY]
            if props:
                return props
        except Exception as exc:  # noqa: BLE001
            print(f"[electrify_agent] live call failed ({exc}); using offline proposals.")
    return offline.electrify_proposals(site)
