"""End-to-end orchestrator + expert-gate tests (offline / no LLM)."""

from decarb.agents import orchestrator
from decarb.storage import load_site
from decarb.validation import (
    ExpertDecision,
    ExpertStatus,
    Guardrails,
    apply_decision,
    evaluate,
)

SCENARIO = "data/demo_office.json"


def _roadmap():
    return orchestrator.run(load_site(SCENARIO), live=False)


def test_roadmap_reduces_emissions_within_budget():
    site = load_site(SCENARIO)
    rm = orchestrator.run(site, live=False)
    assert rm.final_inventory.operational_market < rm.baseline_inventory.operational_market
    assert rm.total_capex <= site.budget_capex + 1e-6
    assert rm.measures, "expected at least one selected measure"


def test_demo_reaches_net_zero_operational():
    rm = _roadmap()
    # The seeded demo is designed to reach ~100% operational (market-based).
    assert rm.pct_to_net_zero > 99.0


def test_every_measure_has_audit_trail():
    rm = _roadmap()
    for m in rm.measures:
        assert m.assumptions, f"measure {m.name} has no audit assumptions"
        # Engineering computed the number, not the proposal.
        assert m.tco2e_delta >= 0


def test_location_based_residual_remains():
    # A PPA cleans market-based S2 but not the physical (location-based) grid use.
    rm = _roadmap()
    assert rm.final_inventory.operational_location > 0


def test_pareto_is_monotonic():
    rm = _roadmap()
    pts = sorted(rm.pareto, key=lambda p: p.capex)
    for a, b in zip(pts, pts[1:]):
        assert b.tco2e_reduction >= a.tco2e_reduction - 1e-6


def test_year_phasing_within_horizon():
    rm = _roadmap()
    for m in rm.measures:
        assert m.year is not None
        assert rm.base_year <= m.year <= rm.target_year


def test_expert_gate_clean_by_default():
    rm = _roadmap()
    site = load_site(SCENARIO)
    violations = evaluate(rm, Guardrails.from_site(site))
    assert violations == []


def test_expert_gate_capex_violation():
    rm = _roadmap()
    g = Guardrails(max_capex=1000.0)  # tiny budget -> violation
    violations = evaluate(rm, g)
    assert any(v.code == "capex_exceeded" for v in violations)


def test_expert_reject_clears_roadmap():
    rm = _roadmap()
    site = load_site(SCENARIO)
    out = apply_decision(rm, site, ExpertDecision(status=ExpertStatus.REJECTED,
                                                  reviewer="t"))
    assert out.measures == []
    assert out.final_inventory.operational_market == rm.baseline_inventory.operational_market


def test_expert_edit_removes_measure_and_rebuilds():
    rm = _roadmap()
    site = load_site(SCENARIO)
    target = rm.measures[0].name
    out = apply_decision(rm, site, ExpertDecision(
        status=ExpertStatus.EDITED, reviewer="t", removed_measure_names=[target]))
    assert all(m.name != target for m in out.measures)
    # Removing an abating measure cannot improve the final result.
    assert out.final_inventory.operational_market >= rm.final_inventory.operational_market - 1e-6
