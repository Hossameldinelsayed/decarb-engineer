"""Reduce agent — proposes efficiency measures (lowers Scope 1 & 2 demand)."""

from __future__ import annotations

from ..models.measure import MeasureProposal, Pillar
from ..models.site import SiteProfile
from . import base, offline

SYSTEM = """You are an energy-efficiency engineer on a decarbonization team.
Propose ONLY 'reduce' (efficiency) measures that cut the building's electricity
or fuel demand. Use action types: lighting_retrofit, hvac_upgrade, bms_controls,
envelope, plug_load_mgmt. For each, set params {"reduction": fraction 0..0.8} of
the targeted end-use. Be realistic and conservative; respect comfort. Do NOT
estimate kWh, cost or CO2 — only propose the action and its reduction fraction.
Return 2-5 proposals via the submit_proposals tool."""


def propose(site: SiteProfile, live: bool | None = None) -> list[MeasureProposal]:
    use_live = base.is_live() if live is None else live
    if use_live:
        try:
            batch = base.call_agent(SYSTEM, base.site_summary(site))
            props = [p for p in batch.to_measure_proposals() if p.pillar == Pillar.REDUCE]
            if props:
                return props
        except Exception as exc:  # noqa: BLE001 - any failure -> deterministic fallback
            print(f"[reduce_agent] live call failed ({exc}); using offline proposals.")
    return offline.reduce_proposals(site)
