"""Human-in-the-loop validation gate.

Nothing is "approved/deployed" without an explicit expert decision. The expert
sets guardrails; the orchestrator's roadmap is checked against them; violations
and per-measure flags are surfaced for the expert to approve / edit / reject.
The decision is logged for auditability.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from ..engineering import apply_measure, build_inventory, state_from_site
from ..models.ghg import GHGInventory
from ..models.roadmap import Roadmap, YearSummary
from ..models.site import SiteProfile


class Guardrails(BaseModel):
    """Constraints the expert imposes before approving a roadmap."""

    max_capex: float | None = None
    max_grid_import_kwh: float | None = None
    min_pct_to_net_zero: float = 0.0
    # If true, any measure carrying a feasibility/safety flag must be reviewed
    # (treated as a blocking violation until the expert clears it).
    block_flagged_measures: bool = False

    @classmethod
    def from_site(cls, site: SiteProfile) -> "Guardrails":
        return cls(
            max_capex=site.budget_capex,
            max_grid_import_kwh=site.constraints.max_grid_import_kwh,
            min_pct_to_net_zero=0.0,
        )


class Violation(BaseModel):
    code: str
    message: str


class ExpertStatus(str, Enum):
    APPROVED = "approved"
    EDITED = "edited"
    REJECTED = "rejected"


class ExpertDecision(BaseModel):
    status: ExpertStatus
    reviewer: str = "unknown"
    notes: str = ""
    # For EDITED decisions: measure names to drop from the roadmap.
    removed_measure_names: list[str] = Field(default_factory=list)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def _grid_import_kwh(inv: GHGInventory) -> float:
    for line in inv.lines:
        if line.scope == "2_location":
            return line.activity_kwh
    return 0.0


def evaluate(roadmap: Roadmap, guardrails: Guardrails) -> list[Violation]:
    """Check a roadmap against guardrails. Empty list = clean."""
    violations: list[Violation] = []

    if guardrails.max_capex is not None and roadmap.total_capex > guardrails.max_capex + 1e-6:
        violations.append(Violation(
            code="capex_exceeded",
            message=(f"Total capex ${roadmap.total_capex:,.0f} exceeds limit "
                     f"${guardrails.max_capex:,.0f}."),
        ))

    if guardrails.max_grid_import_kwh is not None:
        final_import = _grid_import_kwh(roadmap.final_inventory)
        if final_import > guardrails.max_grid_import_kwh + 1e-6:
            violations.append(Violation(
                code="grid_import_exceeded",
                message=(f"Final grid import {final_import:,.0f} kWh exceeds limit "
                         f"{guardrails.max_grid_import_kwh:,.0f} kWh."),
            ))

    if roadmap.pct_to_net_zero < guardrails.min_pct_to_net_zero - 1e-6:
        violations.append(Violation(
            code="ambition_shortfall",
            message=(f"Roadmap reaches {roadmap.pct_to_net_zero:.1f}% to net-zero, "
                     f"below required {guardrails.min_pct_to_net_zero:.1f}%."),
        ))

    if guardrails.block_flagged_measures:
        for m in roadmap.measures:
            if m.flags:
                violations.append(Violation(
                    code="flagged_measure",
                    message=f"'{m.name}' has flags requiring review: {'; '.join(m.flags)}",
                ))

    return violations


def _rebuild(site: SiteProfile, kept: list) -> tuple[GHGInventory, list[YearSummary]]:
    """Recompute final inventory and yearly trajectory for a kept measure set."""
    baseline_state = state_from_site(site)
    baseline_inv = build_inventory(baseline_state)

    final_state = baseline_state.copy()
    for m in kept:
        final_state = apply_measure(final_state, m)
    final_inv = build_inventory(final_state)

    base_op = baseline_inv.operational_market
    summaries: list[YearSummary] = []
    for y in range(site.base_year, site.target_year + 1):
        state = baseline_state.copy()
        cum = capex_y = 0.0
        for m in kept:
            if m.year is not None and m.year <= y:
                state = apply_measure(state, m)
                cum += m.capex
                if m.year == y:
                    capex_y += m.capex
        inv = build_inventory(state)
        pct = 0.0 if base_op <= 1e-9 else 100.0 * (base_op - inv.operational_market) / base_op
        summaries.append(YearSummary(
            year=y, capex_this_year=capex_y, cumulative_capex=cum,
            inventory=inv, pct_reduction_vs_baseline=pct,
            gap_to_net_zero_tco2e=inv.operational_market,
        ))
    return final_inv, summaries


def apply_decision(roadmap: Roadmap, site: SiteProfile,
                   decision: ExpertDecision) -> Roadmap:
    """Return the roadmap as the expert left it.

    APPROVED -> unchanged. REJECTED -> measures cleared (nothing deployed).
    EDITED   -> named measures removed and the trajectory recomputed.
    """
    if decision.status == ExpertStatus.APPROVED:
        return roadmap

    if decision.status == ExpertStatus.REJECTED:
        rejected = roadmap.model_copy(deep=True)
        rejected.measures = []
        rejected.final_inventory = roadmap.baseline_inventory
        rejected.yearly = []
        return rejected

    # EDITED
    kept = [m for m in roadmap.measures if m.name not in decision.removed_measure_names]
    final_inv, yearly = _rebuild(site, kept)
    edited = roadmap.model_copy(deep=True)
    edited.measures = kept
    edited.final_inventory = final_inv
    edited.yearly = yearly
    return edited


def record_decision(roadmap: Roadmap, decision: ExpertDecision,
                    guardrails: Guardrails, violations: list[Violation],
                    log_path: str = "decision_log.json") -> dict:
    """Persist an audit entry of the expert decision. Returns the entry."""
    from ..storage import append_decision_log

    entry = {
        "timestamp": decision.timestamp,
        "site": roadmap.site_name,
        "reviewer": decision.reviewer,
        "status": decision.status.value,
        "notes": decision.notes,
        "removed_measures": decision.removed_measure_names,
        "guardrails": guardrails.model_dump(),
        "violations": [v.model_dump() for v in violations],
        "roadmap_capex": roadmap.total_capex,
        "roadmap_pct_to_net_zero": roadmap.pct_to_net_zero,
        "generated_with": roadmap.generated_with,
    }
    append_decision_log(entry, log_path)
    return entry
