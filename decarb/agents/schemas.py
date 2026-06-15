"""Structured-output schema the LLM agents must return (validated by pydantic).

Agents return INTENT only (pillar, action, knobs). They never return emissions
or cost numbers — those are computed by the engineering layer.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..models.measure import ActionType, MeasureProposal, Pillar


class AgentProposal(BaseModel):
    pillar: Pillar
    action_type: ActionType
    name: str = Field(..., description="Short measure name.")
    rationale: str = Field("", description="Why this measure fits the site.")
    params: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Action knobs. lighting_retrofit/hvac_upgrade/bms_controls/"
            "envelope/plug_load_mgmt -> {'reduction': 0..0.8}. "
            "electrify_end_use -> {'target': '<fossil end-use name>'}. "
            "rooftop_pv -> {'roof_fraction': 0..1} or {'kwp': <number>}. "
            "battery_storage -> {'battery_kwh': <number>}. "
            "green_procurement -> {'coverage_fraction': 0..1}."
        ),
    )


class ProposalBatch(BaseModel):
    proposals: list[AgentProposal] = Field(default_factory=list)

    def to_measure_proposals(self) -> list[MeasureProposal]:
        return [
            MeasureProposal(
                pillar=p.pillar,
                action_type=p.action_type,
                name=p.name,
                rationale=p.rationale,
                params=p.params,
                source="agent",
            )
            for p in self.proposals
        ]
