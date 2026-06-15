"""Orchestrator — coordinate the pillar agents and build a scored roadmap.

Flow:
  1. Build the baseline GHG inventory (deterministic).
  2. Gather candidate proposals from the reduce / electrify / replace agents
     (live LLM if a key is set, else offline canned proposals).
  3. Score each candidate against the EVOLVING site state (the pillars are
     coupled: electrifying adds load, reducing shrinks it, replacing cleans it).
  4. Select measures under the capex budget using the energy hierarchy:
     Reduce -> Electrify -> Replace (PV -> battery -> procurement).
  5. Phase the selected measures across the planning horizon and compute the
     year-by-year trajectory to net zero, plus a cost/carbon Pareto frontier.

Selection metric: the *blended operational* reduction
  Delta(operational_location) + Delta(operational_market).
This credits real abatement (efficiency, PV, electrification — which cut BOTH
Scope 2 methods) more than certificate procurement (a PPA cleans only the
market-based figure), so the roadmap doesn't collapse to "just buy a PPA".
"""

from __future__ import annotations

from ..engineering import apply_measure, build_inventory, score_proposal, state_from_site
from ..engineering.state import SiteState
from ..models.ghg import GHGInventory
from ..models.measure import ActionType, Measure, MeasureProposal, Pillar
from ..models.roadmap import ParetoPoint, Roadmap, YearSummary
from ..models.site import SiteProfile
from . import base, electrify_agent, reduce_agent, replace_agent

_PILLAR_ORDER = [Pillar.REDUCE, Pillar.ELECTRIFY, Pillar.REPLACE]
# Fixed sub-order within Replace: self-generate, then store, then procure residual.
_REPLACE_SUBORDER = {
    ActionType.ROOFTOP_PV: 0,
    ActionType.BATTERY_STORAGE: 1,
    ActionType.GREEN_PROCUREMENT: 2,
}
_EPS = 0.01  # tCO2e threshold below which a measure is "no abatement"


def _selection_score(before: GHGInventory, after: GHGInventory) -> float:
    return ((before.operational_location - after.operational_location)
            + (before.operational_market - after.operational_market))


def gather_proposals(site: SiteProfile, live: bool | None = None) -> list[MeasureProposal]:
    return (
        reduce_agent.propose(site, live)
        + electrify_agent.propose(site, live)
        + replace_agent.propose(site, live)
    )


def _score_on(site: SiteProfile, state: SiteState,
              proposal: MeasureProposal) -> tuple[Measure, SiteState, float]:
    before = build_inventory(state)
    measure, new_state = score_proposal(site, state, proposal)
    after = build_inventory(new_state)
    return measure, new_state, _selection_score(before, after)


def _select(site: SiteProfile, baseline: SiteState,
            proposals: list[MeasureProposal], budget: float
            ) -> tuple[list[Measure], SiteState]:
    """Greedy selection under the energy hierarchy and capex budget."""
    state = baseline.copy()
    selected: list[Measure] = []
    spent = 0.0
    used_groups: set[str] = set()   # exclusive_group -> at most one solution each

    for pillar in _PILLAR_ORDER:
        pool = [p for p in proposals if p.pillar == pillar]

        if pillar == Pillar.REPLACE:
            pool.sort(key=lambda p: _REPLACE_SUBORDER.get(p.action_type, 9))
            for proposal in pool:
                measure, new_state, sel = _score_on(site, state, proposal)
                if sel > _EPS and spent + measure.capex <= budget + 1e-6:
                    selected.append(measure)
                    state, spent = new_state, spent + measure.capex
            continue

        # Reduce / Electrify: greedy by cost-effectiveness (score per $),
        # re-scored on the evolving state each round.
        remaining = list(pool)
        while remaining:
            best_i = best = best_state = None
            best_ratio = 0.0
            for i, proposal in enumerate(remaining):
                group = proposal.params.get("exclusive_group")
                if group and group in used_groups:
                    continue  # an alternative in this group is already chosen
                measure, new_state, sel = _score_on(site, state, proposal)
                if sel <= _EPS or spent + measure.capex > budget + 1e-6:
                    continue
                ratio = sel / max(measure.capex, 1.0)
                if ratio > best_ratio:
                    best_ratio, best_i, best, best_state = ratio, i, measure, new_state
            if best is None:
                break
            selected.append(best)
            state, spent = best_state, spent + best.capex
            group = best.proposal.params.get("exclusive_group")
            if group:
                used_groups.add(group)
            remaining.pop(best_i)

    return selected, state


def _phase_years(site: SiteProfile, baseline: SiteState, baseline_inv: GHGInventory,
                 selected: list[Measure]) -> list[YearSummary]:
    """Assign each measure a year (level annual capex) and build the trajectory."""
    horizon = site.horizon_years
    annual_budget = max(1.0, site.budget_capex / horizon)

    year = site.base_year
    year_spend = 0.0
    for measure in selected:
        if year_spend + measure.capex > annual_budget and year < site.target_year:
            year += 1
            year_spend = 0.0
        measure.year = year
        year_spend += measure.capex

    base_op = baseline_inv.operational_market
    summaries: list[YearSummary] = []
    for y in range(site.base_year, site.target_year + 1):
        state = baseline.copy()
        cum_capex = 0.0
        capex_this_year = 0.0
        for measure in selected:
            if measure.year is not None and measure.year <= y:
                state = apply_measure(state, measure)
                cum_capex += measure.capex
                if measure.year == y:
                    capex_this_year += measure.capex
        inv = build_inventory(state)
        pct = 0.0 if base_op <= 1e-9 else 100.0 * (base_op - inv.operational_market) / base_op
        summaries.append(YearSummary(
            year=y,
            capex_this_year=capex_this_year,
            cumulative_capex=cum_capex,
            inventory=inv,
            pct_reduction_vs_baseline=pct,
            gap_to_net_zero_tco2e=inv.operational_market,
        ))
    return summaries


def _pareto(site: SiteProfile, baseline: SiteState, baseline_inv: GHGInventory,
            proposals: list[MeasureProposal], steps: int = 12) -> list[ParetoPoint]:
    """Cost vs carbon frontier on LOCATION-BASED operational emissions.

    We deliberately use location-based here: it measures REAL, physical abatement
    (efficiency, on-site PV, electrification), which is what capex actually buys.
    A market-based frontier would be degenerate because a ~zero-capex PPA can
    zero out market-based Scope 2 without any physical change to the site.
    """
    base_op = baseline_inv.operational_location
    points: list[ParetoPoint] = []
    seen: set[frozenset[str]] = set()
    for k in range(steps + 1):
        budget = site.budget_capex * k / steps
        selected, final_state = _select(site, baseline, proposals, budget)
        # Dedup on the actual selection identity, NOT its cardinality: different
        # budgets can select different measure sets of the same size, which are
        # genuinely distinct (capex, abatement) points on the frontier.
        key = frozenset(m.name for m in selected)
        if key in seen:
            continue
        seen.add(key)
        final_inv = build_inventory(final_state)
        points.append(ParetoPoint(
            capex=sum(m.capex for m in selected),
            tco2e_reduction=base_op - final_inv.operational_location,
            measure_count=len(selected),
        ))
    return points


def run(site: SiteProfile, live: bool | None = None) -> Roadmap:
    """Produce a complete, scored, multi-year roadmap for the site."""
    baseline_state = state_from_site(site)
    baseline_inv = build_inventory(baseline_state)

    proposals = gather_proposals(site, live)

    # Independent scoring of every candidate on the baseline (transparency table).
    candidates: list[Measure] = []
    for proposal in proposals:
        measure, _ = score_proposal(site, baseline_state, proposal)
        candidates.append(measure)

    selected, final_state = _select(site, baseline_state, proposals, site.budget_capex)
    final_inv = build_inventory(final_state)
    yearly = _phase_years(site, baseline_state, baseline_inv, selected)
    pareto = _pareto(site, baseline_state, baseline_inv, proposals)

    use_live = base.is_live() if live is None else live
    generated_with = f"live ({base.get_model()})" if use_live else "offline"

    return Roadmap(
        site_name=site.name,
        base_year=site.base_year,
        target_year=site.target_year,
        generated_with=generated_with,
        baseline_inventory=baseline_inv,
        final_inventory=final_inv,
        measures=selected,
        yearly=yearly,
        candidates=candidates,
        pareto=pareto,
    )
