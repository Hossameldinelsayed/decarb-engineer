"""Streamlit UI for the Decarbonization Engineer.

Run with:  streamlit run app/streamlit_app.py

Sections:
  (a) GHG baseline by scope
  (b) Proposed roadmap with per-measure tCO2e / cost
  (c) Path to net-zero chart
  (d) Expert approval panel (the mandatory human gate)
"""

from __future__ import annotations

import sys
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

# Make the package importable when run via `streamlit run app/streamlit_app.py`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from decarb.agents import orchestrator  # noqa: E402
from decarb.agents.base import is_live  # noqa: E402
from decarb.models.site import SiteProfile  # noqa: E402
from decarb.storage import load_site  # noqa: E402
from decarb.validation import (  # noqa: E402
    ExpertDecision,
    ExpertStatus,
    Guardrails,
    apply_decision,
    evaluate,
    record_decision,
)

DEMO = Path(__file__).resolve().parents[1] / "data" / "demo_office.json"

st.set_page_config(page_title="Decarbonization Engineer", layout="wide")
st.title("🌍 Decarbonization Engineer")
st.caption("Agentic Reduce / Replace / Electrify roadmaps — auditable to the GHG "
           "Protocol, with a human expert as the final gate. "
           "Agents propose; the deterministic engineering layer computes every number.")


# --------------------------------------------------------------------------- #
# Sidebar: scenario + run controls
# --------------------------------------------------------------------------- #
def load_base_site() -> SiteProfile:
    uploaded = st.session_state.get("uploaded_json")
    if uploaded:
        return SiteProfile.model_validate_json(uploaded)
    return load_site(DEMO)


with st.sidebar:
    st.header("Scenario")
    up = st.file_uploader("SiteProfile JSON (optional)", type="json")
    if up is not None:
        st.session_state["uploaded_json"] = up.getvalue().decode("utf-8")

    base = load_base_site()

    st.subheader("Overrides")
    elec = st.number_input("Annual electricity (kWh)", value=float(base.annual_electricity_kwh),
                           step=50_000.0, format="%.0f")
    roof = st.number_input("Usable roof area (m²)", value=float(base.roof_area_m2),
                           step=100.0, format="%.0f")
    budget = st.number_input("Capex budget ($)", value=float(base.budget_capex),
                             step=100_000.0, format="%.0f")
    target_year = st.number_input("Target year", value=int(base.target_year),
                                  min_value=base.base_year + 1, max_value=base.base_year + 40)
    green = st.slider("Existing green procurement (fraction)", 0.0, 1.0,
                      float(base.existing_green_fraction), 0.05)
    grid_scale = st.slider("Grid intensity scale", 0.2, 2.0, 1.0, 0.05,
                           help="Scale the whole monthly grid carbon-intensity profile.")

    mode = st.radio("Proposal mode", ["Offline (no API key)", "Live LLM agents"],
                    index=0 if not is_live() else 1)
    if mode.startswith("Live") and not is_live():
        st.warning("No ANTHROPIC_API_KEY detected — will fall back to offline.")

    run_clicked = st.button("▶ Run engine", type="primary", use_container_width=True)

# Build the (possibly overridden) site.
site = base.model_copy(deep=True)
site.annual_electricity_kwh = elec
site.roof_area_m2 = roof
site.budget_capex = budget
site.target_year = int(target_year)
site.existing_green_fraction = green
site.grid.monthly_intensity_kgco2e_per_kwh = [
    v * grid_scale for v in base.grid.monthly_intensity_kgco2e_per_kwh
]

if run_clicked:
    with st.spinner("Designing roadmap…"):
        live = mode.startswith("Live")
        st.session_state["roadmap"] = orchestrator.run(site, live=live)
        st.session_state["site"] = site
        st.session_state.pop("decision_logged", None)

roadmap = st.session_state.get("roadmap")
if roadmap is None:
    st.info("Set your scenario in the sidebar and click **Run engine**. "
            "The seeded demo office runs out of the box with no API key.")
    st.stop()

site = st.session_state["site"]
b = roadmap.baseline_inventory
f = roadmap.final_inventory


# --------------------------------------------------------------------------- #
# (a) GHG baseline by scope
# --------------------------------------------------------------------------- #
st.header("a) GHG baseline by scope")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Scope 1", f"{b.scope1_tco2e:,.0f} t")
c2.metric("Scope 2 (location)", f"{b.scope2_location_tco2e:,.0f} t")
c3.metric("Scope 2 (market)", f"{b.scope2_market_tco2e:,.0f} t")
c4.metric("Scope 3 (manual)", f"{b.scope3_tco2e:,.0f} t")

scopes = ["Scope 1", "Scope 2 (loc)", "Scope 2 (mkt)", "Scope 3"]
fig_base = go.Figure()
fig_base.add_bar(name="Baseline", x=scopes,
                 y=[b.scope1_tco2e, b.scope2_location_tco2e, b.scope2_market_tco2e, b.scope3_tco2e])
fig_base.add_bar(name=f"After roadmap ({roadmap.target_year})", x=scopes,
                 y=[f.scope1_tco2e, f.scope2_location_tco2e, f.scope2_market_tco2e, f.scope3_tco2e])
fig_base.update_layout(barmode="group", yaxis_title="tCO2e / yr", height=380,
                       legend=dict(orientation="h"))
st.plotly_chart(fig_base, use_container_width=True)

with st.expander("Audit trail — baseline ledger lines (activity × factor)"):
    st.dataframe(
        [{"scope": L.scope, "source": L.source, "activity_kWh": round(L.activity_kwh),
          "factor_kg/kWh": L.factor_kgco2e_per_kwh, "tCO2e": round(L.tco2e, 2),
          "note": L.note} for L in b.lines],
        use_container_width=True, hide_index=True,
    )


# --------------------------------------------------------------------------- #
# (b) Proposed roadmap
# --------------------------------------------------------------------------- #
st.header("b) Proposed roadmap")
m1, m2, m3 = st.columns(3)
m1.metric("Operational reduction", f"{roadmap.operational_reduction_tco2e:,.0f} t",
          f"{roadmap.pct_to_net_zero:.0f}% to net-zero")
m2.metric("Total capex", f"${roadmap.total_capex:,.0f}",
          f"budget ${site.budget_capex:,.0f}")
m3.metric("Residual (location-based)", f"{f.operational_location:,.0f} t",
          help="Physical grid dependence remaining after the roadmap.")
st.caption(f"Proposals generated: **{roadmap.generated_with}**")

st.dataframe(
    [{"year": m.year, "pillar": m.pillar.value, "measure": m.name,
      "capex $": round(m.capex), "tCO2e/yr": round(m.tco2e_delta, 1),
      "$/tCO2e": (None if m.cost_per_tco2e == float("inf") else round(m.cost_per_tco2e)),
      "flags": "; ".join(m.flags)} for m in roadmap.measures],
    use_container_width=True, hide_index=True,
)

with st.expander("Per-measure audit trail"):
    for m in roadmap.measures:
        st.markdown(f"**{m.name}** ({m.pillar.value}) — scopes {', '.join(m.scopes_affected)}")
        for a in m.assumptions:
            st.markdown(f"- {a}")


# --------------------------------------------------------------------------- #
# (c) Path to net-zero + cost/carbon frontier
# --------------------------------------------------------------------------- #
st.header("c) Path to net-zero")
years = [ys.year for ys in roadmap.yearly]

left, right = st.columns(2)
with left:
    fig_path = go.Figure()
    fig_path.add_scatter(x=years, y=[ys.inventory.scope1_tco2e for ys in roadmap.yearly],
                         stackgroup="o", name="Scope 1")
    fig_path.add_scatter(x=years, y=[ys.inventory.scope2_market_tco2e for ys in roadmap.yearly],
                         stackgroup="o", name="Scope 2 (market)")
    fig_path.add_scatter(x=years, y=[0 for _ in years], name="Net-zero target",
                         line=dict(dash="dash", color="green"))
    fig_path.update_layout(title="Operational emissions (S1 + S2 market)",
                           yaxis_title="tCO2e / yr", height=380, legend=dict(orientation="h"))
    st.plotly_chart(fig_path, use_container_width=True)

with right:
    pts = sorted(roadmap.pareto, key=lambda p: p.capex)
    fig_par = go.Figure()
    fig_par.add_scatter(x=[p.capex for p in pts], y=[p.tco2e_reduction for p in pts],
                        mode="lines+markers", name="Frontier")
    fig_par.update_layout(title="Cost vs real (location-based) abatement",
                          xaxis_title="Cumulative capex ($)",
                          yaxis_title="tCO2e/yr avoided", height=380)
    st.plotly_chart(fig_par, use_container_width=True)


# --------------------------------------------------------------------------- #
# (d) Expert approval panel
# --------------------------------------------------------------------------- #
st.header("d) Expert validation gate")
st.caption("Nothing is deployed without an explicit expert decision. "
           "Set guardrails, review violations, then approve / edit / reject.")

g1, g2, g3 = st.columns(3)
max_capex = g1.number_input("Guardrail: max capex ($)", value=float(site.budget_capex),
                            step=100_000.0, format="%.0f")
min_pct = g2.slider("Guardrail: min % to net-zero", 0.0, 100.0, 0.0, 5.0)
block_flagged = g3.checkbox("Block flagged measures", value=False)

guardrails = Guardrails(
    max_capex=max_capex,
    max_grid_import_kwh=site.constraints.max_grid_import_kwh,
    min_pct_to_net_zero=min_pct,
    block_flagged_measures=block_flagged,
)
violations = evaluate(roadmap, guardrails)

if violations:
    for v in violations:
        st.error(f"[{v.code}] {v.message}")
else:
    st.success("No guardrail violations.")

reviewer = st.text_input("Reviewer name", value="A. Expert")
notes = st.text_area("Notes", value="")
remove = st.multiselect("Measures to remove (for an EDIT decision)",
                        [m.name for m in roadmap.measures])

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
    st.session_state["decision_logged"] = entry
    st.success(f"Decision **{decision.status.value.upper()}** by {reviewer} "
               f"recorded at {decision.timestamp}. Logged to decision_log.json.")
    st.json(entry)
    if decision.status != ExpertStatus.APPROVED:
        st.rerun()
