"""Schneider-branded Streamlit UI for the Decarbonization Engineer.

Run with:  streamlit run app/streamlit_app.py

Flow (matches the business priority):
  Step 1 - REDUCE    : Schneider efficiency solutions, priced EUR/m2 x floor area
  Step 2 - REPLACE   : clean supply (rooftop PV, storage, green PPA)
  Step 3 - ELECTRIFY : ask whether the site has gas heating / a genset / a fleet
  Then               : net-zero trajectory + the mandatory expert gate
"""

from __future__ import annotations

import sys
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from decarb.agents import orchestrator  # noqa: E402
from decarb.agents.base import is_live  # noqa: E402
from decarb.catalog import load_catalog  # noqa: E402
from decarb.engineering import score_proposal, state_from_site  # noqa: E402
from decarb.models.measure import ActionType, MeasureProposal, Pillar  # noqa: E402
from decarb.models.site import (  # noqa: E402
    ElectrificationMethod,
    ElectrificationOption,
    EndUseBreakdown,
    FossilEndUse,
    FuelType,
    GridProfile,
    SiteProfile,
    Tariff,
)
from decarb.validation import (  # noqa: E402
    ExpertDecision,
    ExpertStatus,
    Guardrails,
    apply_decision,
    evaluate,
    record_decision,
)

# Schneider brand palette.
SE_GREEN = "#3DCD58"
SE_GREEN_DARK = "#1C7A3B"
SE_INK = "#0E2A1B"

st.set_page_config(page_title="Schneider Decarbonization Engineer", layout="wide",
                   page_icon="🌿")

# --- Schneider-branded header + background -------------------------------------
st.markdown(f"""
<style>
  .stApp {{ background: linear-gradient(180deg, #EAF7EE 0%, #F1FAF3 240px, #FFFFFF 100%); }}
  .se-band {{ background: {SE_INK}; border-left: 10px solid {SE_GREEN};
             padding: 18px 22px; border-radius: 8px; margin-bottom: 8px; }}
  .se-band h1 {{ color: #FFFFFF; margin: 0; font-size: 26px; }}
  .se-band p  {{ color: {SE_GREEN}; margin: 4px 0 0 0; font-weight: 600; letter-spacing: .5px; }}
  .se-step {{ background: {SE_GREEN}; color: {SE_INK}; padding: 6px 14px;
             border-radius: 6px; font-weight: 700; display: inline-block; }}
  div[data-testid="stMetricValue"] {{ color: {SE_GREEN_DARK}; }}
</style>
<div class="se-band">
  <h1>🌿 Decarbonization Engineer</h1>
  <p>SCHNEIDER ELECTRIC &nbsp;|&nbsp; REDUCE &rsaquo; REPLACE &rsaquo; ELECTRIFY</p>
</div>
""", unsafe_allow_html=True)
st.caption("Agents propose Schneider solutions; a deterministic engine computes "
           "every kWh, tCO₂e and € (auditable to the GHG Protocol). Pricing is "
           "illustrative EUR/m², not an official quote. Human expert approves before deploy.")


# --- Sidebar: building inputs --------------------------------------------------
with st.sidebar:
    st.markdown("### 🏢 Building")
    name = st.text_input("Site name", "Schneider Impact Office")
    floor_area = st.number_input("Floor area (m²)", min_value=100.0, value=12000.0,
                                 step=500.0, format="%.0f",
                                 help="Drives both carbon reduction and total €/m² price.")
    intensity = st.number_input("Electricity use (kWh/m²/yr)", min_value=10.0, value=150.0,
                                step=5.0)
    annual_elec = floor_area * intensity
    st.caption(f"→ {annual_elec:,.0f} kWh/yr total electricity")

    with st.expander("Electricity end-use mix"):
        hvac = st.slider("HVAC", 0.0, 1.0, 0.45, 0.05)
        lighting = st.slider("Lighting", 0.0, 1.0, 0.20, 0.05)
        plug = st.slider("Plug loads", 0.0, 1.0, 0.25, 0.05)
        other = max(0.0, round(1.0 - hvac - lighting - plug, 2))
        st.caption(f"Other = {other:.0%} (auto)")

    st.markdown("### ⚡ Grid & tariff")
    grid_avg = st.slider("Grid carbon intensity (kgCO₂e/kWh)", 0.0, 0.8, 0.40, 0.01)
    elec_price = st.number_input("Electricity tariff (€/kWh)", 0.0, 1.0, 0.16, 0.01)

    st.markdown("### 🔥 Fossil end-uses (Electrify step)")
    has_gas = st.checkbox("Gas / oil heating", value=True)
    gas_kwh = st.number_input("  heating fuel (kWh/yr)", 0.0, value=700000.0, step=50000.0,
                              format="%.0f", disabled=not has_gas)
    has_genset = st.checkbox("Diesel / standby generator", value=True)
    genset_kwh = st.number_input("  genset fuel (kWh/yr)", 0.0, value=40000.0, step=10000.0,
                                 format="%.0f", disabled=not has_genset)
    has_fleet = st.checkbox("Combustion vehicle fleet", value=True)
    fleet_kwh = st.number_input("  fleet fuel (kWh/yr)", 0.0, value=120000.0, step=20000.0,
                                format="%.0f", disabled=not has_fleet)

    st.markdown("### 🎯 Targets")
    roof_area = st.number_input("Usable roof area (m²)", 0.0, value=4000.0, step=250.0,
                                format="%.0f")
    budget = st.number_input("Capex budget (€)", 0.0, value=2500000.0, step=100000.0,
                             format="%.0f")
    target_year = st.number_input("Net-zero target year", 2026, 2060, 2035)
    scope3 = st.number_input("Scope 3 (manual, tCO₂e/yr)", 0.0, value=650.0, step=50.0,
                             format="%.0f")
    mode = st.radio("Proposal mode", ["Offline (no API key)", "Live LLM agents"],
                    index=0 if not is_live() else 1)
    run_clicked = st.button("▶ Run engine", type="primary", use_container_width=True)


def build_site() -> SiteProfile:
    fossils: list[FossilEndUse] = []
    if has_gas and gas_kwh > 0:
        fossils.append(FossilEndUse(
            name="Gas / oil heating", fuel_type=FuelType.NATURAL_GAS, annual_fuel_kwh=gas_kwh,
            electrification=ElectrificationOption(method=ElectrificationMethod.HEAT_PUMP)))
    if has_genset and genset_kwh > 0:
        fossils.append(FossilEndUse(
            name="Diesel / standby generator", fuel_type=FuelType.DIESEL, annual_fuel_kwh=genset_kwh,
            electrification=ElectrificationOption(method=ElectrificationMethod.GRID_TIE,
                                                  incumbent_efficiency=0.33)))
    if has_fleet and fleet_kwh > 0:
        fossils.append(FossilEndUse(
            name="Combustion vehicle fleet", fuel_type=FuelType.DIESEL, annual_fuel_kwh=fleet_kwh,
            electrification=ElectrificationOption(method=ElectrificationMethod.EV_FLEET,
                                                  incumbent_efficiency=1.0)))
    return SiteProfile(
        name=name, floor_area_m2=floor_area, annual_electricity_kwh=annual_elec,
        end_use_breakdown=EndUseBreakdown(hvac=hvac, lighting=lighting, plug_loads=plug, other=other),
        fossil_end_uses=fossils,
        grid=GridProfile(monthly_intensity_kgco2e_per_kwh=[grid_avg] * 12),
        tariff=Tariff(electricity_price_per_kwh=elec_price),
        roof_area_m2=roof_area, scope3_tco2e=scope3,
        target_year=int(target_year), budget_capex=budget,
    )


if run_clicked:
    with st.spinner("Designing roadmap…"):
        site = build_site()
        st.session_state["site"] = site
        st.session_state["roadmap"] = orchestrator.run(site, live=mode.startswith("Live"))
        st.session_state.pop("decision_logged", None)

if "roadmap" not in st.session_state:
    st.info("Set the building in the sidebar and click **▶ Run engine**. "
            "Defaults reproduce the demo office.")
    st.stop()

site: SiteProfile = st.session_state["site"]
roadmap = st.session_state["roadmap"]
b, f = roadmap.baseline_inventory, roadmap.final_inventory
EUR = "€{:,.0f}".format


# =============================================================================
# STEP 1 — REDUCE  (the priority pillar)
# =============================================================================
st.markdown('<span class="se-step">STEP 1 · REDUCE</span>', unsafe_allow_html=True)
st.subheader("Schneider efficiency solutions — priced per m²")

# Score every catalog solution independently on the baseline for the menu.
baseline_state = state_from_site(site)
catalog = load_catalog()
menu_rows = []
for sol in catalog.reduce:
    if not any(site.end_use_breakdown.share(u) > 0 for u in sol.target_end_uses):
        continue
    prop = MeasureProposal(pillar=Pillar.REDUCE, action_type=ActionType.EFFICIENCY_SOLUTION,
                           name=sol.name, params={"solution_id": sol.id})
    m, _ = score_proposal(site, baseline_state, prop)
    menu_rows.append({
        "Solution": sol.name, "Schneider product": sol.product,
        "Targets": ", ".join(sol.target_end_uses),
        "€/m²": sol.capex_eur_per_m2, "Total price €": round(m.capex),
        "kWh saved/yr": round(-m.electricity_kwh_delta), "tCO₂e/yr": round(m.tco2e_delta, 1),
    })
st.caption(f"Building floor area **{site.floor_area_m2:,.0f} m²** → total price = €/m² × area, "
           "for each solution scored on this building.")
st.dataframe(menu_rows, use_container_width=True, hide_index=True)

reduce_measures = [m for m in roadmap.measures if m.pillar == Pillar.REDUCE]
reduce_capex = sum(m.capex for m in reduce_measures)
reduce_tco2e = sum(m.tco2e_delta for m in reduce_measures)
reduce_kwh = sum(-m.electricity_kwh_delta for m in reduce_measures)
base_building_elec = site.annual_electricity_kwh

r1, r2, r3, r4 = st.columns(4)
r1.metric("Recommended solutions", f"{len(reduce_measures)}")
r2.metric("Reduce total price", EUR(reduce_capex))
r3.metric("Electricity saved", f"{reduce_kwh:,.0f} kWh",
          f"{(reduce_kwh / base_building_elec * 100 if base_building_elec else 0):.0f}% of building")
r4.metric("Carbon cut (Reduce)", f"{reduce_tco2e:,.0f} tCO₂e/yr")
st.caption("Recommended set respects budget and picks at most one building-management "
           "system. Expand any measure below for its audit trail.")
with st.expander("Recommended Reduce solutions — audit trail"):
    for m in reduce_measures:
        st.markdown(f"**{m.name}** — {EUR(m.capex)} · {m.tco2e_delta:.1f} tCO₂e/yr")
        for a in m.assumptions:
            st.markdown(f"- {a}")


# =============================================================================
# STEP 2 — REPLACE
# =============================================================================
st.markdown('<span class="se-step">STEP 2 · REPLACE</span>', unsafe_allow_html=True)
st.subheader("Clean supply — rooftop PV, storage, green PPA")
replace_measures = [m for m in roadmap.measures if m.pillar == Pillar.REPLACE]
if replace_measures:
    st.dataframe(
        [{"Solution": m.name, "Price €": round(m.capex),
          "PV kWp": round(m.pv_kwp), "tCO₂e/yr": round(m.tco2e_delta, 1),
          "scopes": ", ".join(m.scopes_affected)} for m in replace_measures],
        use_container_width=True, hide_index=True)
else:
    st.caption("No replace measures selected (e.g. no roof area).")


# =============================================================================
# STEP 3 — ELECTRIFY
# =============================================================================
st.markdown('<span class="se-step">STEP 3 · ELECTRIFY</span>', unsafe_allow_html=True)
st.subheader("Remove fossil end-uses (Scope 1)")
electrify_measures = [m for m in roadmap.measures if m.pillar == Pillar.ELECTRIFY]
if not site.fossil_end_uses:
    st.caption("No fossil end-uses declared. Add a gas boiler, generator or fleet in the sidebar.")
elif electrify_measures:
    st.dataframe(
        [{"Solution": m.name, "Price €": round(m.capex),
          "fuel removed kWh": round(-m.fuel_kwh_delta),
          "new electric load kWh": round(m.extra_kwh_delta),
          "tCO₂e/yr": round(m.tco2e_delta, 1)} for m in electrify_measures],
        use_container_width=True, hide_index=True)
else:
    st.caption("Fossil end-uses present but none selected within budget.")


# =============================================================================
# Net-zero summary + trajectory
# =============================================================================
st.divider()
st.subheader("📉 Path to net-zero")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Baseline operational", f"{b.operational_market:,.0f} tCO₂e")
m2.metric("After roadmap", f"{f.operational_market:,.0f} tCO₂e",
          f"-{roadmap.pct_to_net_zero:.0f}% to net-zero")
m3.metric("Total capex", EUR(roadmap.total_capex), f"budget {EUR(site.budget_capex)}")
m4.metric("Residual (location-based)", f"{f.operational_location:,.0f} tCO₂e",
          help="Physical grid dependence remaining after a PPA cleans market-based Scope 2.")

left, right = st.columns(2)
with left:
    scopes = ["Scope 1", "Scope 2 (loc)", "Scope 2 (mkt)", "Scope 3"]
    fig = go.Figure()
    fig.add_bar(name="Baseline", x=scopes,
                y=[b.scope1_tco2e, b.scope2_location_tco2e, b.scope2_market_tco2e, b.scope3_tco2e],
                marker_color="#9AA0A6")
    fig.add_bar(name="After roadmap", x=scopes,
                y=[f.scope1_tco2e, f.scope2_location_tco2e, f.scope2_market_tco2e, f.scope3_tco2e],
                marker_color=SE_GREEN)
    fig.update_layout(barmode="group", yaxis_title="tCO₂e/yr", height=360,
                      legend=dict(orientation="h"))
    st.plotly_chart(fig, use_container_width=True)
with right:
    years = [ys.year for ys in roadmap.yearly]
    figp = go.Figure()
    figp.add_scatter(x=years, y=[ys.inventory.scope1_tco2e for ys in roadmap.yearly],
                     stackgroup="o", name="Scope 1", line=dict(color="#B08968"))
    figp.add_scatter(x=years, y=[ys.inventory.scope2_market_tco2e for ys in roadmap.yearly],
                     stackgroup="o", name="Scope 2 (market)", line=dict(color=SE_GREEN_DARK))
    figp.add_scatter(x=years, y=[0 for _ in years], name="Net-zero",
                     line=dict(dash="dash", color=SE_GREEN))
    figp.update_layout(title="Operational emissions (S1 + S2 market)", yaxis_title="tCO₂e/yr",
                       height=360, legend=dict(orientation="h"))
    st.plotly_chart(figp, use_container_width=True)


# =============================================================================
# Expert validation gate (mandatory)
# =============================================================================
st.divider()
st.markdown('<span class="se-step">EXPERT GATE</span>', unsafe_allow_html=True)
st.caption("Nothing is deployed without an explicit expert decision.")

g1, g2, g3 = st.columns(3)
max_capex = g1.number_input("Max capex (€)", value=float(site.budget_capex), step=100000.0,
                            format="%.0f")
min_pct = g2.slider("Min % to net-zero", 0.0, 100.0, 0.0, 5.0)
block_flagged = g3.checkbox("Block flagged measures", value=False)
guardrails = Guardrails(max_capex=max_capex, min_pct_to_net_zero=min_pct,
                        block_flagged_measures=block_flagged)
violations = evaluate(roadmap, guardrails)
if violations:
    for v in violations:
        st.error(f"[{v.code}] {v.message}")
else:
    st.success("No guardrail violations.")

reviewer = st.text_input("Reviewer name", "A. Expert")
notes = st.text_area("Notes", "")
remove = st.multiselect("Measures to remove (for an edit)", [m.name for m in roadmap.measures])
d1, d2, d3 = st.columns(3)
approve = d1.button("✅ Approve", use_container_width=True)
edit = d2.button("✏️ Approve with edits", use_container_width=True, disabled=not remove)
reject = d3.button("❌ Reject", use_container_width=True)

decision = None
if approve:
    decision = ExpertDecision(status=ExpertStatus.APPROVED, reviewer=reviewer, notes=notes)
elif edit:
    decision = ExpertDecision(status=ExpertStatus.EDITED, reviewer=reviewer, notes=notes,
                              removed_measure_names=remove)
elif reject:
    decision = ExpertDecision(status=ExpertStatus.REJECTED, reviewer=reviewer, notes=notes)

if decision is not None:
    result = apply_decision(roadmap, site, decision)
    entry = record_decision(result, decision, guardrails, violations)
    st.session_state["roadmap"] = result
    st.success(f"Decision **{decision.status.value.upper()}** by {reviewer} logged at "
               f"{decision.timestamp}.")
    st.json(entry)
    if decision.status != ExpertStatus.APPROVED:
        st.rerun()
