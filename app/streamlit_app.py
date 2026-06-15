"""AI Decarbonization Engineer - Schneider-branded Streamlit UI.

Run with:  streamlit run app/streamlit_app.py

Layout:
  Hero
  Solution Architecture (EcoStruxure 3 layers: Onboard -> Operate -> Optimize)
  Step 1 REDUCE  (Schneider efficiency solutions, priced EUR/m2 x floor area)
  Step 2 REPLACE (clean supply: PV, storage, green PPA)
  Step 3 ELECTRIFY (asks about gas heating / generator / fleet)
  Path to net-zero
  Schneider Solution Architect approval (the mandatory human gate)
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

SE_GREEN = "#3DCD58"
SE_GREEN_DARK = "#1C7A3B"
SE_INK = "#0B2A1A"

st.set_page_config(page_title="AI Decarbonization Engineer", layout="wide", page_icon="🟢")

# --------------------------------------------------------------------------- #
# Design system (Schneider brand) + animations
# --------------------------------------------------------------------------- #
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"], .stApp, button, input, textarea { font-family: 'Inter', sans-serif !important; }
.stApp {
  background:
    radial-gradient(1100px 480px at 8% -8%, #D9F3E0 0%, rgba(217,243,224,0) 62%),
    linear-gradient(180deg, #F4FBF6 0%, #FFFFFF 60%);
}
#MainMenu, footer {visibility: hidden;}
.block-container { padding-top: 1.6rem; }

@keyframes fadeUp { from{opacity:0; transform:translateY(16px);} to{opacity:1; transform:none;} }
@keyframes popIn { from{opacity:0; transform:scale(.95);} to{opacity:1; transform:none;} }
@keyframes sheen { 0%{transform:translateX(-40%) rotate(18deg);} 60%,100%{transform:translateX(320%) rotate(18deg);} }
@keyframes barfill { from{width:0;} }
@keyframes shimmer { 0%{background-position:-300px 0;} 100%{background-position:300px 0;} }

/* ---- hero ---- */
.hero { position:relative; overflow:hidden; border-radius:22px; padding:34px 40px; color:#fff;
        background:linear-gradient(120deg,#08230F 0%,#114026 48%,#2E8B4E 100%);
        box-shadow:0 22px 46px rgba(8,35,15,.30); animation:fadeUp .7s ease both; }
.hero::after { content:''; position:absolute; top:-60%; left:0; width:45%; height:220%;
        background:linear-gradient(90deg,rgba(255,255,255,0),rgba(61,205,88,.20),rgba(255,255,255,0));
        animation:sheen 7s ease-in-out infinite; }
.hero .tag { color:#8FE6A4; font-weight:800; letter-spacing:3px; font-size:11.5px; }
.hero h1 { font-size:32px; font-weight:800; margin:6px 0 0; letter-spacing:-.6px; }
.hero p { margin:12px 0 0; color:#CFE9D6; max-width:820px; font-size:14px; line-height:1.55; }
.hero .badges { margin-top:16px; }
.hero .badge { display:inline-block; margin-right:8px; background:rgba(61,205,88,.16);
        border:1px solid rgba(61,205,88,.5); color:#D6F6DD; padding:6px 13px; border-radius:999px;
        font-size:12px; font-weight:700; }

/* ---- section label ---- */
.steplab { display:inline-flex; align-items:center; gap:8px; background:""" + SE_GREEN + """;
        color:#08230F; font-weight:800; padding:7px 16px; border-radius:999px; font-size:13px;
        letter-spacing:.4px; box-shadow:0 8px 18px rgba(61,205,88,.38); animation:popIn .5s ease both; }
.sub { color:#5a6b60; font-size:13.5px; margin:8px 0 4px; }

/* ---- 3-layer architecture ---- */
.arch { display:flex; flex-direction:column; gap:12px; margin:10px 0 6px; }
.layer { border-radius:16px; padding:15px 20px; color:#fff; box-shadow:0 12px 26px rgba(11,42,26,.16);
        transition:transform .25s ease, box-shadow .25s ease; animation:fadeUp .6s ease both; }
.layer:hover { transform:translateY(-5px); box-shadow:0 18px 36px rgba(11,42,26,.26); }
.layer .lhead { display:flex; align-items:baseline; gap:10px; }
.layer .lname { font-weight:800; font-size:16px; letter-spacing:.4px; }
.layer .lkicker { font-size:11.5px; font-weight:700; opacity:.85; letter-spacing:1px; }
.layer .ldesc { font-size:12.5px; opacity:.92; margin:3px 0 11px; }
.layer.optimize { background:linear-gradient(120deg,#08230F,#1C7A3B); }
.layer.operate  { background:linear-gradient(120deg,#1C7A3B,#2EA24A); }
.layer.onboard  { background:linear-gradient(120deg,#2EA24A,#3DCD58); color:#08230F; }
.chip { display:inline-block; background:rgba(255,255,255,.18); border:1px solid rgba(255,255,255,.40);
        padding:5px 12px; border-radius:999px; font-size:12px; font-weight:600; margin:4px 6px 2px 0;
        animation:popIn .5s ease both; }
.layer.onboard .chip { background:rgba(8,35,15,.10); border-color:rgba(8,35,15,.25); }
.chip.empty { opacity:.65; font-style:italic; border-style:dashed; background:transparent; }

/* ---- net-zero progress bar ---- */
.nz { height:16px; border-radius:999px; background:#E4EFE8; overflow:hidden; box-shadow:inset 0 1px 3px rgba(0,0,0,.08); }
.nz-fill { height:100%; border-radius:999px; background:linear-gradient(90deg,#1C7A3B,#3DCD58);
        animation:barfill 1.1s cubic-bezier(.2,.7,.2,1) both; position:relative; }
.nz-fill::after { content:''; position:absolute; inset:0;
        background:linear-gradient(90deg,rgba(255,255,255,0),rgba(255,255,255,.45),rgba(255,255,255,0));
        background-size:300px 100%; animation:shimmer 2.2s linear infinite; }

/* ---- metrics + buttons ---- */
div[data-testid="stMetric"] { background:#fff; border:1px solid #E6EFE9; border-radius:14px;
        padding:14px 16px; box-shadow:0 6px 16px rgba(13,58,36,.06);
        transition:transform .2s ease, box-shadow .2s ease; animation:fadeUp .6s ease both; }
div[data-testid="stMetric"]:hover { transform:translateY(-3px); box-shadow:0 14px 26px rgba(13,58,36,.13); }
div[data-testid="stMetricValue"] { color:#16713a; font-weight:800; }
.stButton>button { border-radius:11px; font-weight:700; transition:all .2s ease; }
.stButton>button:hover { transform:translateY(-2px); box-shadow:0 10px 20px rgba(61,205,88,.32); }
[data-testid="stSidebar"] { background:linear-gradient(180deg,#FFFFFF,#F1FAF3); }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero">
  <div class="tag">SCHNEIDER ELECTRIC &nbsp;|&nbsp; ECOSTRUXURE</div>
  <h1>AI Decarbonization Engineer</h1>
  <p>AI agents propose Schneider solutions; a deterministic engine computes every kWh, tCO&#8322;e and &euro;,
     auditable to the GHG Protocol. A Schneider Solution Architect approves this AI engineer&#39;s work before
     anything is deployed.</p>
  <div class="badges">
    <span class="badge">REDUCE</span><span class="badge">REPLACE</span><span class="badge">ELECTRIFY</span>
    <span class="badge">Onboard &rsaquo; Operate &rsaquo; Optimize</span>
  </div>
</div>
""", unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Sidebar inputs
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.markdown("### Building")
    name = st.text_input("Site name", "Schneider Impact Office")
    floor_area = st.number_input("Floor area (m²)", min_value=100.0, value=12000.0, step=500.0,
                                 format="%.0f", help="Drives carbon reduction and the €/m² total price.")
    intensity = st.number_input("Electricity use (kWh/m²/yr)", min_value=10.0, value=150.0, step=5.0)
    annual_elec = floor_area * intensity
    st.caption(f"= {annual_elec:,.0f} kWh/yr total electricity")
    with st.expander("Electricity end-use mix"):
        hvac = st.slider("HVAC", 0.0, 1.0, 0.45, 0.05)
        lighting = st.slider("Lighting", 0.0, 1.0, 0.20, 0.05)
        plug = st.slider("Plug loads", 0.0, 1.0, 0.25, 0.05)
        other = max(0.0, round(1.0 - hvac - lighting - plug, 2))
        st.caption(f"Other = {other:.0%} (auto)")

    st.markdown("### Grid and tariff")
    grid_avg = st.slider("Grid carbon intensity (kgCO₂e/kWh)", 0.0, 0.8, 0.40, 0.01)
    elec_price = st.number_input("Electricity tariff (€/kWh)", 0.0, 1.0, 0.16, 0.01)

    st.markdown("### Fossil end-uses  ·  Electrify step")
    has_gas = st.checkbox("Gas / oil heating", value=True)
    gas_kwh = st.number_input("heating fuel (kWh/yr)", 0.0, value=700000.0, step=50000.0,
                              format="%.0f", disabled=not has_gas)
    has_genset = st.checkbox("Diesel / standby generator", value=True)
    genset_kwh = st.number_input("genset fuel (kWh/yr)", 0.0, value=40000.0, step=10000.0,
                                 format="%.0f", disabled=not has_genset)
    has_fleet = st.checkbox("Combustion vehicle fleet", value=True)
    fleet_kwh = st.number_input("fleet fuel (kWh/yr)", 0.0, value=120000.0, step=20000.0,
                                format="%.0f", disabled=not has_fleet)

    st.markdown("### Targets")
    roof_area = st.number_input("Usable roof area (m²)", 0.0, value=4000.0, step=250.0, format="%.0f")
    budget = st.number_input("Capex budget (€)", 0.0, value=2500000.0, step=100000.0, format="%.0f")
    target_year = st.number_input("Net-zero target year", 2026, 2060, 2035)
    scope3 = st.number_input("Scope 3 (manual, tCO₂e/yr)", 0.0, value=650.0, step=50.0, format="%.0f")
    mode = st.radio("Proposal mode", ["Offline (no API key)", "Live LLM agents"],
                    index=0 if not is_live() else 1)
    run_clicked = st.button("Run AI engine", type="primary", use_container_width=True)


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
        target_year=int(target_year), budget_capex=budget)


if run_clicked:
    with st.spinner("AI agents designing the roadmap…"):
        site = build_site()
        st.session_state["site"] = site
        st.session_state["roadmap"] = orchestrator.run(site, live=mode.startswith("Live"))
        st.session_state.pop("decision_logged", None)

if "roadmap" not in st.session_state:
    st.info("Set the building in the sidebar and click **Run AI engine**. "
            "Defaults reproduce the demo office.")
    st.stop()

site: SiteProfile = st.session_state["site"]
roadmap = st.session_state["roadmap"]
b, f = roadmap.baseline_inventory, roadmap.final_inventory
catalog = load_catalog()
EUR = "€{:,.0f}".format

reduce_measures = [m for m in roadmap.measures if m.pillar == Pillar.REDUCE]
replace_measures = [m for m in roadmap.measures if m.pillar == Pillar.REPLACE]
electrify_measures = [m for m in roadmap.measures if m.pillar == Pillar.ELECTRIFY]


def short(label: str) -> str:
    s = label.split(" (")[0].split(" + ")[0].strip()
    return s if len(s) <= 42 else s[:40] + "…"


# --------------------------------------------------------------------------- #
# Solution Architecture (EcoStruxure 3 layers)
# --------------------------------------------------------------------------- #
st.markdown('<span class="steplab">SOLUTION ARCHITECT</span>', unsafe_allow_html=True)
st.markdown('<div class="sub">EcoStruxure architecture for the recommended roadmap: '
            'Onboard (connect &amp; measure) at the base, Operate (control) in the middle, '
            'Optimize (analytics, clean supply &amp; electrification) on top.</div>',
            unsafe_allow_html=True)

layers: dict[str, list[str]] = {"optimize": [], "operate": [], "onboard": []}
for m in reduce_measures:
    sol = catalog.reduce_by_id(m.proposal.params.get("solution_id", ""))
    layers.get(sol.layer if sol else "operate", layers["operate"]).append(short(m.name))
for m in replace_measures + electrify_measures:
    layers["optimize"].append(short(m.name))


def _chips(items: list[str]) -> str:
    if not items:
        return '<span class="chip empty">no selected solution in this layer</span>'
    return "".join(
        f'<span class="chip" style="animation-delay:{i*0.05:.2f}s" title="{c}">{c}</span>'
        for i, c in enumerate(items))


def _layer(key: str, kicker: str, name: str, desc: str, delay: float) -> str:
    return (f'<div class="layer {key}" style="animation-delay:{delay:.2f}s">'
            f'<div class="lhead"><span class="lname">{name}</span>'
            f'<span class="lkicker">{kicker}</span></div>'
            f'<div class="ldesc">{desc}</div>{_chips(layers[key])}</div>')


st.markdown(
    '<div class="arch">'
    + _layer("optimize", "OPTIMIZE", "Apps, Analytics &amp; Services",
             "Advisory, fault-detection analytics, clean supply and electrification.", 0.0)
    + _layer("operate", "OPERATE", "Edge Control",
             "Building management, room control and drives running the building efficiently.", 0.08)
    + _layer("onboard", "ONBOARD", "Connected Products",
             "Meter, sense and connect to build the data foundation.", 0.16)
    + "</div>", unsafe_allow_html=True)

# Headline KPIs + animated net-zero bar.
k1, k2, k3, k4 = st.columns(4)
k1.metric("To net-zero (operational)", f"{roadmap.pct_to_net_zero:.0f}%")
k2.metric("Total capex", EUR(roadmap.total_capex), f"budget {EUR(site.budget_capex)}")
k3.metric("Reduce price (per m² × area)", EUR(sum(m.capex for m in reduce_measures)))
k4.metric("Carbon cut", f"{roadmap.operational_reduction_tco2e:,.0f} tCO₂e/yr")
pct = max(0.0, min(100.0, roadmap.pct_to_net_zero))
st.markdown(f'<div class="nz"><div class="nz-fill" style="width:{pct:.1f}%"></div></div>',
            unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Step 1 REDUCE
# --------------------------------------------------------------------------- #
st.write("")
st.markdown('<span class="steplab">STEP 1 · REDUCE</span>', unsafe_allow_html=True)
st.markdown('<div class="sub">Schneider efficiency solutions priced per m². '
            f'Floor area <b>{site.floor_area_m2:,.0f} m²</b>, so total price = €/m² × area.</div>',
            unsafe_allow_html=True)

baseline_state = state_from_site(site)
menu_rows = []
for sol in catalog.reduce:
    if not any(site.end_use_breakdown.share(u) > 0 for u in sol.target_end_uses):
        continue
    prop = MeasureProposal(pillar=Pillar.REDUCE, action_type=ActionType.EFFICIENCY_SOLUTION,
                           name=sol.name, params={"solution_id": sol.id})
    m, _ = score_proposal(site, baseline_state, prop)
    menu_rows.append({
        "Solution": sol.name, "Schneider product": sol.product, "Layer": sol.layer,
        "Targets": ", ".join(sol.target_end_uses), "€/m²": sol.capex_eur_per_m2,
        "Total price €": round(m.capex), "kWh saved/yr": round(-m.electricity_kwh_delta),
        "tCO₂e/yr": round(m.tco2e_delta, 1)})
st.dataframe(menu_rows, use_container_width=True, hide_index=True)

reduce_kwh = sum(-m.electricity_kwh_delta for m in reduce_measures)
r1, r2, r3, r4 = st.columns(4)
r1.metric("Recommended solutions", f"{len(reduce_measures)}")
r2.metric("Reduce total price", EUR(sum(m.capex for m in reduce_measures)))
r3.metric("Electricity saved", f"{reduce_kwh:,.0f} kWh",
          f"{(reduce_kwh / site.annual_electricity_kwh * 100 if site.annual_electricity_kwh else 0):.0f}% of building")
r4.metric("Carbon cut (Reduce)", f"{sum(m.tco2e_delta for m in reduce_measures):,.0f} tCO₂e/yr")
with st.expander("Recommended Reduce solutions · audit trail"):
    for m in reduce_measures:
        st.markdown(f"**{m.name}**  ·  {EUR(m.capex)}  ·  {m.tco2e_delta:.1f} tCO₂e/yr")
        for a in m.assumptions:
            st.markdown(f"- {a}")


# --------------------------------------------------------------------------- #
# Step 2 REPLACE
# --------------------------------------------------------------------------- #
st.write("")
st.markdown('<span class="steplab">STEP 2 · REPLACE</span>', unsafe_allow_html=True)
st.markdown('<div class="sub">Clean supply: rooftop PV, storage and a green PPA.</div>',
            unsafe_allow_html=True)
if replace_measures:
    st.dataframe(
        [{"Solution": m.name, "Price €": round(m.capex), "PV kWp": round(m.pv_kwp),
          "tCO₂e/yr": round(m.tco2e_delta, 1), "scopes": ", ".join(m.scopes_affected)}
         for m in replace_measures], use_container_width=True, hide_index=True)
else:
    st.caption("No replace measures selected (e.g. no roof area).")


# --------------------------------------------------------------------------- #
# Step 3 ELECTRIFY
# --------------------------------------------------------------------------- #
st.write("")
st.markdown('<span class="steplab">STEP 3 · ELECTRIFY</span>', unsafe_allow_html=True)
st.markdown('<div class="sub">Remove fossil end-uses (Scope 1). '
            'Declare gas heating, a generator or a fleet in the sidebar.</div>',
            unsafe_allow_html=True)
if not site.fossil_end_uses:
    st.caption("No fossil end-uses declared.")
elif electrify_measures:
    st.dataframe(
        [{"Solution": m.name, "Price €": round(m.capex),
          "fuel removed kWh": round(-m.fuel_kwh_delta),
          "new electric load kWh": round(m.extra_kwh_delta), "tCO₂e/yr": round(m.tco2e_delta, 1)}
         for m in electrify_measures], use_container_width=True, hide_index=True)
else:
    st.caption("Fossil end-uses present but none selected within budget.")


# --------------------------------------------------------------------------- #
# Path to net-zero
# --------------------------------------------------------------------------- #
st.write("")
st.markdown('<span class="steplab">PATH TO NET-ZERO</span>', unsafe_allow_html=True)
m1, m2, m3 = st.columns(3)
m1.metric("Baseline operational", f"{b.operational_market:,.0f} tCO₂e")
m2.metric("After roadmap", f"{f.operational_market:,.0f} tCO₂e", f"-{roadmap.pct_to_net_zero:.0f}%")
m3.metric("Residual (location-based)", f"{f.operational_location:,.0f} tCO₂e",
          help="Physical grid dependence after a PPA cleans market-based Scope 2.")

CHART_MARGIN = dict(l=64, r=24, t=36, b=96)
left, right = st.columns(2)
with left:
    scopes = ["Scope 1", "Scope 2<br>location", "Scope 2<br>market", "Scope 3"]
    fig = go.Figure()
    fig.add_bar(name="Baseline", x=scopes,
                y=[b.scope1_tco2e, b.scope2_location_tco2e, b.scope2_market_tco2e, b.scope3_tco2e],
                marker_color="#AEB7B0")
    fig.add_bar(name="After roadmap", x=scopes,
                y=[f.scope1_tco2e, f.scope2_location_tco2e, f.scope2_market_tco2e, f.scope3_tco2e],
                marker_color=SE_GREEN)
    fig.update_layout(barmode="group", bargap=0.32, bargroupgap=0.12, height=400,
                      margin=CHART_MARGIN, title="GHG baseline by scope",
                      yaxis_title="tCO₂e / yr", plot_bgcolor="rgba(0,0,0,0)",
                      paper_bgcolor="rgba(0,0,0,0)",
                      legend=dict(orientation="h", y=-0.22, x=0.5, xanchor="center"))
    fig.update_xaxes(tickfont=dict(size=12), ticklen=8)
    fig.update_yaxes(gridcolor="#E6EFE9", zeroline=False)
    st.plotly_chart(fig, use_container_width=True)
with right:
    years = [ys.year for ys in roadmap.yearly]
    figp = go.Figure()
    figp.add_scatter(x=years, y=[ys.inventory.scope1_tco2e for ys in roadmap.yearly],
                     stackgroup="o", name="Scope 1", mode="lines",
                     line=dict(width=0.5, color="#C09A6B"), fillcolor="rgba(192,154,107,.55)")
    figp.add_scatter(x=years, y=[ys.inventory.scope2_market_tco2e for ys in roadmap.yearly],
                     stackgroup="o", name="Scope 2 market", mode="lines",
                     line=dict(width=0.5, color=SE_GREEN_DARK), fillcolor="rgba(46,162,74,.55)")
    figp.add_scatter(x=years, y=[0 for _ in years], name="Net-zero", mode="lines",
                     line=dict(dash="dash", color=SE_GREEN, width=2))
    figp.update_layout(height=400, margin=CHART_MARGIN, title="Operational emissions (S1 + S2 market)",
                       yaxis_title="tCO₂e / yr", plot_bgcolor="rgba(0,0,0,0)",
                       paper_bgcolor="rgba(0,0,0,0)",
                       legend=dict(orientation="h", y=-0.22, x=0.5, xanchor="center"))
    figp.update_xaxes(tickfont=dict(size=12), dtick=2)
    figp.update_yaxes(gridcolor="#E6EFE9", zeroline=False)
    st.plotly_chart(figp, use_container_width=True)


# --------------------------------------------------------------------------- #
# Final consolidated solution table
# --------------------------------------------------------------------------- #
st.write("")
st.markdown('<span class="steplab">RECOMMENDED SOLUTIONS</span>', unsafe_allow_html=True)
st.dataframe(
    [{"Year": m.year, "Pillar": m.pillar.value, "Solution": m.name,
      "Price €": round(m.capex), "tCO₂e/yr": round(m.tco2e_delta, 1),
      "€/tCO₂e": (None if m.cost_per_tco2e == float("inf") else round(m.cost_per_tco2e))}
     for m in roadmap.measures], use_container_width=True, hide_index=True)


# --------------------------------------------------------------------------- #
# Schneider Solution Architect approval (mandatory gate)
# --------------------------------------------------------------------------- #
st.write("")
st.markdown('<span class="steplab">SCHNEIDER SOLUTION ARCHITECT · APPROVAL</span>',
            unsafe_allow_html=True)
st.markdown('<div class="sub">The Schneider Solution Architect approves this AI engineer&#39;s work '
            'first. Nothing is deployed without an explicit decision.</div>', unsafe_allow_html=True)

g1, g2, g3 = st.columns(3)
max_capex = g1.number_input("Max capex (€)", value=float(site.budget_capex), step=100000.0, format="%.0f")
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

reviewer = st.text_input("Solution Architect name", "A. Architect")
notes = st.text_area("Notes", "")
remove = st.multiselect("Solutions to remove (for an edit)", [m.name for m in roadmap.measures])
d1, d2, d3 = st.columns(3)
approve = d1.button("Approve", use_container_width=True)
edit = d2.button("Approve with edits", use_container_width=True, disabled=not remove)
reject = d3.button("Reject", use_container_width=True)

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
