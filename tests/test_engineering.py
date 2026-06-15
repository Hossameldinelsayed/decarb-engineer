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


def test_lighting_retrofit_saves_targeted_share():
    site = _site()
    state = state_from_site(site)
    p = MeasureProposal(pillar=Pillar.REDUCE, action_type=ActionType.LIGHTING_RETROFIT,
                        name="LED", params={"reduction": 0.5})
    m, _ = score_proposal(site, state, p)
    # lighting share 0.20 of 1,800,000 = 360,000; 50% cut = 180,000 kWh saved.
    assert math.isclose(m.electricity_kwh_delta, -180_000, rel_tol=1e-6)
    assert m.tco2e_delta > 0  # less grid import -> emissions avoided


def test_efficiency_reduction_capped():
    site = _site()
    state = state_from_site(site)
    p = MeasureProposal(pillar=Pillar.REDUCE, action_type=ActionType.HVAC_UPGRADE,
                        name="HVAC", params={"reduction": 0.99})
    m, _ = score_proposal(site, state, p)
    assert any("capped" in f.lower() for f in m.flags)


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
