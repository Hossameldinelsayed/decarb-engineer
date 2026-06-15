"""Carbon ledger tests — the auditable core. Numbers are hand-checked."""

from decarb.engineering.carbon import build_inventory, pv_self_consumption_kwh
from decarb.engineering.state import FossilUseState, SiteState


def _state(**kw) -> SiteState:
    base = dict(
        electricity_demand_kwh=1_000_000,
        fossil_uses=[],
        grid_avg_intensity=0.4,
        market_residual_factor=0.4,
        scope3_tco2e=0.0,
    )
    base.update(kw)
    return SiteState(**base)


def test_scope2_location_basic():
    inv = build_inventory(_state())
    # 1,000,000 kWh * 0.4 kg/kWh = 400,000 kg = 400 t
    assert inv.scope2_location_tco2e == 400.0
    assert inv.scope2_market_tco2e == 400.0  # no procurement -> same


def test_scope1_fuel():
    inv = build_inventory(_state(fossil_uses=[
        FossilUseState("Gas", "natural_gas", 500_000, 0.184),
    ]))
    assert round(inv.scope1_tco2e, 3) == round(500_000 * 0.184 / 1000, 3)  # 92.0 t


def test_ppa_cuts_market_only():
    # Procure all grid import -> market-based 0, location-based unchanged.
    inv = build_inventory(_state(ppa_rec_kwh=1_000_000))
    assert inv.scope2_market_tco2e == 0.0
    assert inv.scope2_location_tco2e == 400.0


def test_pv_self_consumption_displaces_import():
    # PV bigger than coincident load: only the daytime-coincident share counts
    # without storage.
    sc = pv_self_consumption_kwh(pv_generation_kwh=500_000,
                                 demand_kwh=1_000_000, battery_kwh=0)
    assert sc == 500_000 * 0.65  # PV_DAYTIME_COINCIDENCE
    inv = build_inventory(_state(pv_generation_kwh=500_000))
    grid_import = 1_000_000 - sc
    assert round(inv.scope2_location_tco2e, 3) == round(grid_import * 0.4 / 1000, 3)


def test_battery_lifts_self_consumption():
    no_batt = pv_self_consumption_kwh(800_000, 1_000_000, 0)
    with_batt = pv_self_consumption_kwh(800_000, 1_000_000, 500)
    assert with_batt > no_batt
    assert with_batt <= min(800_000, 1_000_000)


def test_totals_compose():
    inv = build_inventory(_state(
        fossil_uses=[FossilUseState("Gas", "natural_gas", 500_000, 0.184)],
        scope3_tco2e=100.0,
    ))
    assert round(inv.total_market_based, 3) == round(
        inv.scope1_tco2e + inv.scope2_market_tco2e + inv.scope3_tco2e, 3)
    assert round(inv.operational_market, 3) == round(
        inv.scope1_tco2e + inv.scope2_market_tco2e, 3)
