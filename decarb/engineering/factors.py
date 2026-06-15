"""Centralised emission & cost factors — the single audit basis for the engine.

ALL numbers the engine produces trace back to a factor defined here plus an
activity value from the SiteProfile. These are transparent, illustrative MVP
defaults (order-of-magnitude correct, not site-specific). In a production
deployment these would come from the SE tools listed in `adapters.py` and from
recognised factor databases (e.g. IPCC / DEFRA / national grid datasets).

Sources of magnitude (illustrative):
  - Natural gas ~0.184 kgCO2e/kWh, diesel ~0.267, LPG ~0.214 (DEFRA-style ranges).
  - PV capex ~$900/kWp installed (commercial rooftop).
  - Battery capex ~$350/kWh installed.
"""

from __future__ import annotations

from ..models.site import FuelType

# --- Scope 1 fuel emission factors (kgCO2e per kWh of fuel) -----------------
FUEL_EMISSION_FACTORS: dict[FuelType, float] = {
    FuelType.NATURAL_GAS: 0.184,
    FuelType.DIESEL: 0.267,
    FuelType.LPG: 0.214,
    FuelType.FUEL_OIL: 0.267,
    FuelType.PETROL: 0.249,
}

# --- PV / supply assumptions ------------------------------------------------
# Usable rooftop PV density (kWp per m2 of usable roof). ~6 m2/kWp -> ~0.17.
PV_KWP_PER_M2 = 0.17
# Specific yield (kWh generated per kWp per year). Site/latitude dependent;
# overridden per-site via the grid profile if desired. ~1100 = temperate EU.
PV_SPECIFIC_YIELD_KWH_PER_KWP = 1100.0
# Fraction of PV generation that coincides with daytime load WITHOUT storage
# (offices load well with solar). Drives self-consumption in carbon.py.
PV_DAYTIME_COINCIDENCE = 0.65

# --- Battery assumptions ----------------------------------------------------
BATTERY_CYCLES_PER_YEAR = 300.0
BATTERY_ROUND_TRIP_EFFICIENCY = 0.90

# --- Capex factors ----------------------------------------------------------
PV_CAPEX_PER_KWP = 900.0
BATTERY_CAPEX_PER_KWH = 350.0
# Efficiency retrofit capex, expressed per annual kWh saved (illustrative).
#   Lighting (LED) is cheap per kWh saved; HVAC/envelope progressively dearer.
EFFICIENCY_CAPEX_PER_KWH_SAVED: dict[str, float] = {
    "lighting_retrofit": 0.45,
    "hvac_upgrade": 1.20,
    "bms_controls": 0.30,
    "envelope": 2.50,
    "plug_load_mgmt": 0.20,
}
# Heat-pump capex per kW of *electric* capacity installed (illustrative).
HEAT_PUMP_CAPEX_PER_KW_ELECTRIC = 1200.0
# Assumed equivalent full-load hours/yr to size electrical kW from annual kWh.
ELECTRIC_HEAT_FULL_LOAD_HOURS = 1800.0
# EV fleet conversion capex per annual electric kWh of new charging load.
EV_FLEET_CAPEX_PER_KWH = 1.50
# Genset->grid tie-in capex per annual kWh displaced.
GRID_TIE_CAPEX_PER_KWH = 0.20

# --- Green procurement (PPA / REC) ------------------------------------------
# PPAs are typically opex (price/kWh) not capex; we model a small contracting
# capex and a per-kWh opex premium so it appears in cost, but the dominant
# effect is on market-based Scope 2. Set capex ~0 to reflect reality.
PPA_CAPEX_PER_KWH = 0.0
PPA_OPEX_PREMIUM_PER_KWH = 0.0   # assume price-neutral PPA for the MVP

# --- Efficiency improvement caps (sanity guards on agent proposals) ---------
MAX_EFFICIENCY_REDUCTION = 0.80   # cannot cut an end use by more than 80%
