"""Offline (no-LLM) proposal generators.

These let the whole pipeline run end-to-end with ZERO API key. They inspect the
SiteProfile and emit sensible candidate *intents* per pillar. Crucially they
emit proposals only — every kWh / tCO2e / $ is still computed by the
deterministic engineering layer, exactly as for live LLM proposals.
"""

from __future__ import annotations

from ..models.measure import ActionType, MeasureProposal, Pillar
from ..models.site import SiteProfile

SOURCE = "offline"


def reduce_proposals(site: SiteProfile) -> list[MeasureProposal]:
    eub = site.end_use_breakdown
    out: list[MeasureProposal] = []
    if eub.lighting > 0:
        out.append(MeasureProposal(
            pillar=Pillar.REDUCE, action_type=ActionType.LIGHTING_RETROFIT,
            name="LED lighting retrofit + daylight controls",
            rationale="Lighting is a fast-payback efficiency win.",
            params={"reduction": 0.55}, source=SOURCE,
        ))
    if eub.hvac > 0:
        out.append(MeasureProposal(
            pillar=Pillar.REDUCE, action_type=ActionType.BMS_CONTROLS,
            name="BMS optimisation & setpoint tuning",
            rationale="Low-cost controls trim HVAC energy with no comfort loss.",
            params={"reduction": 0.15}, source=SOURCE,
        ))
        out.append(MeasureProposal(
            pillar=Pillar.REDUCE, action_type=ActionType.HVAC_UPGRADE,
            name="High-efficiency HVAC plant upgrade",
            rationale="Replace ageing chillers/AHUs with high-COP equipment.",
            params={"reduction": 0.30}, source=SOURCE,
        ))
    if eub.plug_loads > 0:
        out.append(MeasureProposal(
            pillar=Pillar.REDUCE, action_type=ActionType.PLUG_LOAD_MGMT,
            name="Smart plug-load management",
            rationale="Scheduling and standby control on plug loads.",
            params={"reduction": 0.20}, source=SOURCE,
        ))
    return out


def electrify_proposals(site: SiteProfile) -> list[MeasureProposal]:
    out: list[MeasureProposal] = []
    for use in site.fossil_end_uses:
        if not use.electrifiable:
            continue
        out.append(MeasureProposal(
            pillar=Pillar.ELECTRIFY, action_type=ActionType.ELECTRIFY_END_USE,
            name=f"Electrify: {use.name}",
            rationale=f"Remove Scope 1 from {use.name} by switching to electric.",
            params={"target": use.name}, source=SOURCE,
        ))
    return out


def replace_proposals(site: SiteProfile) -> list[MeasureProposal]:
    out: list[MeasureProposal] = []
    if site.roof_area_m2 > 0:
        out.append(MeasureProposal(
            pillar=Pillar.REPLACE, action_type=ActionType.ROOFTOP_PV,
            name="Rooftop solar PV (full usable roof)",
            rationale="On-site generation displaces grid import.",
            params={"roof_fraction": 1.0}, source=SOURCE,
        ))
        out.append(MeasureProposal(
            pillar=Pillar.REPLACE, action_type=ActionType.BATTERY_STORAGE,
            name="Battery storage to lift self-consumption",
            rationale="Shift daytime PV surplus into evening load.",
            params={"battery_kwh": 800}, source=SOURCE,
        ))
    out.append(MeasureProposal(
        pillar=Pillar.REPLACE, action_type=ActionType.GREEN_PROCUREMENT,
        name="Green power PPA for residual grid import",
        rationale="Clean the remaining grid electricity (market-based Scope 2).",
        params={"coverage_fraction": 1.0}, source=SOURCE,
    ))
    return out


def all_proposals(site: SiteProfile) -> list[MeasureProposal]:
    return reduce_proposals(site) + electrify_proposals(site) + replace_proposals(site)
