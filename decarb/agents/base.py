"""Anthropic agent plumbing: live structured-JSON calls with an offline fallback.

The agents use tool-use *forcing* so the model is obliged to return JSON that
validates against `ProposalBatch`. If no API key is present (or the SDK/network
fails), callers fall back to the deterministic offline proposals.
"""

from __future__ import annotations

import json
import os

from ..models.site import SiteProfile
from .schemas import ProposalBatch

DEFAULT_MODEL = "claude-opus-4-8"


def get_model() -> str:
    return os.environ.get("DECARB_AGENT_MODEL", DEFAULT_MODEL)


def is_live() -> bool:
    """True if a live LLM call is possible (key present and SDK importable)."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def site_summary(site: SiteProfile) -> str:
    """Compact, numeric site description for the agent prompt (no targets given)."""
    eub = site.end_use_breakdown
    fossils = "; ".join(
        f"{u.name} ({u.fuel_type.value}, {u.annual_fuel_kwh:,.0f} kWh/yr, "
        f"electrifiable={u.electrifiable})"
        for u in site.fossil_end_uses
    ) or "none"
    return (
        f"Site: {site.name} in {site.location}\n"
        f"Floor area: {site.floor_area_m2:,.0f} m2\n"
        f"Annual electricity: {site.annual_electricity_kwh:,.0f} kWh\n"
        f"Electricity end-use shares: HVAC {eub.hvac:.0%}, lighting {eub.lighting:.0%}, "
        f"plug {eub.plug_loads:.0%}, other {eub.other:.0%}\n"
        f"Fossil end-uses: {fossils}\n"
        f"Grid carbon intensity (avg): {site.grid.annual_average:.3f} kgCO2e/kWh\n"
        f"Usable roof area: {site.roof_area_m2:,.0f} m2\n"
        f"Electricity tariff: {site.tariff.electricity_price_per_kwh:.3f} $/kWh\n"
        f"Capex budget: ${site.budget_capex:,.0f}\n"
        f"Horizon: {site.base_year}->{site.target_year}\n"
        f"Comfort/constraints: {site.constraints.comfort_note or 'none stated'}"
    )


def call_agent(system_prompt: str, user_prompt: str,
               max_tokens: int = 2000) -> ProposalBatch:
    """Make a live structured call. Raises on any failure (caller handles fallback)."""
    import anthropic

    client = anthropic.Anthropic()
    tool = {
        "name": "submit_proposals",
        "description": "Submit the list of proposed decarbonization measures.",
        "input_schema": ProposalBatch.model_json_schema(),
    }
    resp = client.messages.create(
        model=get_model(),
        max_tokens=max_tokens,
        system=system_prompt,
        tools=[tool],
        tool_choice={"type": "tool", "name": "submit_proposals"},
        messages=[{"role": "user", "content": user_prompt}],
    )
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "submit_proposals":
            return ProposalBatch.model_validate(block.input)
    # Defensive: no tool_use returned.
    raise RuntimeError("Agent did not return structured proposals via the tool: "
                       f"{json.dumps([getattr(b, 'type', '?') for b in resp.content])}")
