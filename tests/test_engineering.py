"""Tests for the deterministic engineering models (reduce / electrify / supply)."""

import math

from decarb.engineering import score_proposal, state_from_site
from decarb.engineering.factors import (
    PV_KWP_PER_M2,
    PV_SPECIFIC_YIELD_KWH_PER_KWP,
)
from decarb.models.measure import ActionType, MeasureProposal, Pillar
from decarb.storage import load_site

SCENARIO = "data/demo_office.json"


def _site():
    return load_site(SCENARIO)


def test_led_solution_saves_targeted_end_use():
    # Catalog 'led_lighting' targets lighting at 55%.
    site = _site()
    state = state_from_site(site)
    p = MeasureProposal(pillar=Pillar.REDUCE, action_type=ActionType.EFFICIENCY_SOLUTION,
                        name="LED", params={"solution_id": "led_lighting"})
    m, _ = score_proposal(site, state, p)
    # lighting share 0.20 of 1,800,000 = 360,000; 55% cut = 198,000 kWh saved.
    assert math.isclose(m.electricity_kwh_delta, -198_000, rel_tol=1e-6)
    assert m.end_use_deltas["lighting"] < 0
    assert m.tco2e_delta > 0


def test_efficiency_priced_per_m2():
    # Total price = EUR/m2 x floor area, driven by building size.
    from decarb.catalog import load_catalog
    site = _site()
    state = state_from_site(site)
    sol = load_catalog().reduce_by_id("led_lighting")
    p = MeasureProposal(pillar=Pillar.REDUCE, action_type=ActionType.EFFICIENCY_SOLUTION,
                        name="LED", params={"solution_id": "led_lighting"})
    m, _ = score_proposal(site, state, p)
    assert math.isclose(m.capex, sol.capex_eur_per_m2 * site.floor_area_m2, rel_tol=1e-9)


def test_stacked_hvac_solutions_have_diminishing_returns():
    # Two HVAC solutions applied in sequence: the second cuts the REMAINING HVAC,
    # so combined savings are less than the naive sum (accurate stacking).
    site = _site()
    state = state_from_site(site)
    p1 = MeasureProposal(pillar=Pillar.REDUCE, action_type=ActionType.EFFICIENCY_SOLUTION,
                         name="VSD", params={"solution_id": "vsd_drives"})
    m1, s1 = score_proposal(site, state, p1)
    p2 = MeasureProposal(pillar=Pillar.REDUCE, action_type=ActionType.EFFICIENCY_SOLUTION,
                         name="BMS", params={"solution_id": "bms_ebo"})
    m2_after, _ = score_proposal(site, s1, p2)      # scored on the reduced state
    m2_fresh, _ = score_proposal(site, state, p2)   # scored on the original state
    assert abs(m2_after.end_use_deltas["hvac"]) < abs(m2_fresh.end_use_deltas["hvac"])


def test_electrify_gas_removes_scope1_adds_load():
    site = _site()
    state = state_from_site(site)
    p = MeasureProposal(pillar=Pillar.ELECTRIFY, action_type=ActionType.ELECTRIFY_END_USE,
                        name="HP", params={"target": "Gas space heating"})
    m, new_state = score_proposal(site, state, p)
    # Heat pump: 700,000 * 0.88 / 3.2 = 192,500 kWh electric added.
    assert math.isclose(m.electricity_kwh_delta, 700_000 * 0.88 / 3.2, rel_tol=1e-6)
    assert math.isclose(m.fuel_kwh_delta, -700_000, rel_tol=1e-6)
    # Gas removed from the new state.
    assert new_state.find_fossil("Gas space heating").fuel_kwh == 0.0
    assert m.tco2e_delta > 0


def test_pv_sized_from_roof():
    site = _site()
    state = state_from_site(site)
    p = MeasureProposal(pillar=Pillar.REPLACE, action_type=ActionType.ROOFTOP_PV,
                        name="PV", params={"roof_fraction": 1.0})
    m, _ = score_proposal(site, state, p)
    expected_kwp = site.roof_area_m2 * PV_KWP_PER_M2
    assert math.isclose(m.pv_kwp, expected_kwp, rel_tol=1e-6)
    assert math.isclose(m.pv_generation_kwh,
                        expected_kwp * PV_SPECIFIC_YIELD_KWH_PER_KWP, rel_tol=1e-6)


def test_pv_capped_to_roof_headroom():
    site = _site()
    state = state_from_site(site)
    p = MeasureProposal(pillar=Pillar.REPLACE, action_type=ActionType.ROOFTOP_PV,
                        name="PV huge", params={"kwp": 10_000})
    m, _ = score_proposal(site, state, p)
    assert m.pv_kwp <= site.roof_area_m2 * PV_KWP_PER_M2 + 1e-6
    assert any("roof headroom" in f.lower() for f in m.flags)


def test_procurement_affects_market_only():
    site = _site()
    state = state_from_site(site)
    p = MeasureProposal(pillar=Pillar.REPLACE, action_type=ActionType.GREEN_PROCUREMENT,
                        name="PPA", params={"coverage_fraction": 1.0})
    m, new_state = score_proposal(site, state, p)
    assert m.scopes_affected == ["2_market"]
    assert m.ppa_rec_kwh > 0
