"""Replace agent — proposes clean-supply measures (PV, storage, procurement)."""

from __future__ import annotations

from ..models.measure import MeasureProposal, Pillar
from ..models.site import SiteProfile
from . import base, offline

SYSTEM = """You are a clean-energy supply engineer on a decarbonization team.
Propose ONLY 'replace' measures that clean the remaining electricity:
- rooftop_pv with params {"roof_fraction": 0..1} (or {"kwp": number})
- battery_storage with params {"battery_kwh": number}
- green_procurement (PPA/REC) with params {"coverage_fraction": 0..1}
Prefer on-site PV first, then storage to lift self-consumption, then a PPA to
cover residual grid import. Do NOT estimate generation, cost or CO2 — the
engineering layer computes them. Return proposals via the submit_proposals tool."""


def propose(site: SiteProfile, live: bool | None = None) -> list[MeasureProposal]:
    use_live = base.is_live() if live is None else live
    if use_live:
        try:
            batch = base.call_agent(SYSTEM, base.site_summary(site))
            props = [p for p in batch.to_measure_proposals() if p.pillar == Pillar.REPLACE]
            if props:
                return props
        except Exception as exc:  # noqa: BLE001
            print(f"[replace_agent] live call failed ({exc}); using offline proposals.")
    return offline.replace_proposals(site)
