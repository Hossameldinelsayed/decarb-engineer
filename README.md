# Decarbonization Engineer

An agentic **"AI decarbonization engineer"** proof-of-concept. Give it a site's
energy + carbon profile and a net-zero target; it **designs and scores** a
multi-year roadmap across three coupled pillars — **Reduce** (efficiency),
**Replace** (clean supply), **Electrify** (remove fossil end-uses) — auditable to
the **GHG Protocol** (Scope 1 / 2 / 3), with a **human expert as the final gate**.

This is an internal concept demo, not a production system.

## Core design principle

> **LLM agents PROPOSE strategies. A deterministic, transparent engineering
> layer COMPUTES the physics (kWh, tCO2e, cost).**

Every emissions number traces to an input value × an explicit factor — the model
never guesses numbers. The proprietary Schneider Electric tools that would do the
heavy engineering in production are **stubbed behind adapter interfaces** with
explicit TODOs; they are not reimplemented.

| Engineering module        | Production tool it stands in for          |
|---------------------------|-------------------------------------------|
| `efficiency.py`           | **IES** (building energy simulation)      |
| `electrify.py`            | **AVEVA Process Simulation**              |
| `supply.py` (PV/interconnect) | **ETAP** (electrical)                 |
| `supply.py` / `carbon.py` (dispatch) | **EcoStruxure Microgrid Advisor** |
| `carbon.py` (GHG ledger)  | **EcoStruxure Resource Advisor**          |

(See `decarb/engineering/adapters.py` for the seam.)

## Architecture

```
decarb/
  models/        pydantic data models (SiteProfile, GHGInventory, Measure, Roadmap)
  engineering/   deterministic physics — NO LLM
    factors.py     all emission & cost factors (the single audit basis)
    carbon.py      GHG ledger: Scope 1, Scope 2 (location + market), Scope 3
    efficiency.py  Reduce pillar
    electrify.py   Electrify pillar
    supply.py      Replace pillar (PV / battery / PPA)
    simulate.py    score a proposal (marginal tCO2e) + apply it to a state
    adapters.py    Protocol interfaces for the SE tools above
  agents/        LLM agents (Anthropic SDK) — return structured JSON proposals
    reduce_agent.py  electrify_agent.py  replace_agent.py
    orchestrator.py  coordinates agents, scores on the coupled state, builds roadmap
    offline.py       deterministic canned proposals (no API key needed)
  validation/    expert_gate.py — guardrails, approve / edit / reject, audit log
  cli.py         command-line entry point
  storage.py     scenarios / roadmaps / decision log <-> JSON
app/             streamlit_app.py — the UI
data/            demo_office.json — seeded mid-size office scenario
tests/           pytest suite (carbon math, engineering, end-to-end)
```

## GHG accounting rules implemented

- **Reduce** → lowers Scope 2 (less purchased electricity) and any Scope 1.
- **Electrify** → drives Scope 1 toward 0 by replacing combustion with electric
  load (which *increases* electricity demand, raising Scope 2 until it is cleaned).
- **Replace** → cleans the remaining electricity: on-site PV self-consumption and
  PPA/REC procurement drive **market-based** Scope 2 toward 0. **Location-based**
  Scope 2 is reported separately and reflects the physical grid dependence (a PPA
  does *not* reduce it).
- Scope 1, Scope 2 (both methods) and Scope 3 are reported separately and combined,
  with % reduction vs baseline and the remaining gap to net-zero.

The roadmap targets **net-zero operational emissions (Scope 1 + market-based
Scope 2)**. Scope 3 is a manual input for the MVP and is reported but not abated
by the on-site measures.

## Setup

Requires **Python 3.11+**.

> **Windows note:** make sure you create the venv with a 3.11+ interpreter, not an
> older default `python` (a system Python 3.7 will fail at `ensurepip`). Use the
> `py` launcher — `py -0p` lists installed versions.

```bat
:: Windows (cmd / PowerShell)
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

```bash
# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

If `pip install` fails behind a corporate proxy (e.g. `SSL: WRONG_VERSION_NUMBER`),
configure pip for your proxy or use an offline wheel cache. The CLI and tests need
only `pydantic`; `streamlit` + `plotly` are needed for the UI, `anthropic` only for
`--live` mode.

## Run

### CLI (runs fully offline — no API key needed)

```bash
python -m decarb.cli run --scenario data/demo_office.json
```

Add an explicit expert decision (the gate is mandatory — nothing "deploys"
without one) and save the result:

```bash
python -m decarb.cli run --scenario data/demo_office.json \
    --approve --reviewer "A. Expert" --out out/roadmap.json
```

Useful flags: `--offline` / `--live`, `--min-pct 80` (guardrail),
`--reject`, `--notes "..."`, `--log decision_log.json`.

### Streamlit app

```bash
streamlit run app/streamlit_app.py
```

Shows (a) the GHG baseline by scope, (b) the proposed roadmap with per-measure
tCO2e/cost, (c) the path-to-net-zero chart + cost/carbon frontier, and
(d) the expert approval panel.

### Live LLM agents (optional)

The system runs end-to-end **without any API key** using deterministic canned
proposals. To let Claude propose the measures instead:

```bash
export ANTHROPIC_API_KEY=sk-...        # Windows: set ANTHROPIC_API_KEY=...
pip install anthropic
python -m decarb.cli run --scenario data/demo_office.json --live
```

Agents return **structured JSON** (validated with pydantic via tool-use forcing)
containing only *intent* — pillar, action, and knobs. The engineering layer still
computes every kWh / tCO2e / $. The default model is `claude-opus-4-8` (override
with `DECARB_AGENT_MODEL`). Any live-call failure falls back to offline proposals.

## Demo result (seeded office)

Baseline operational emissions **887 tCO2e/yr** (Scope 1 171.5 + market Scope 2
715.5; Scope 3 650 reported separately). The roadmap reaches **~100% to net-zero
operational** for **~$1.44M** capex, while **location-based** Scope 2 retains
**~305 tCO2e/yr** — surfacing the physical grid dependence behind the
market-based net-zero claim.

## Tests

```bash
pytest -q
```

## Limitations / TODOs (MVP)

- Engineering models are intentionally simple (annual energy balances, an annual
  PV self-consumption heuristic, illustrative factors). They are accurate to
  order-of-magnitude, not to a specific site. Swap in the SE tools via
  `adapters.py` for production fidelity.
- Scope 3 is a manual input; no supply-chain measures are modelled.
- Costs are capex/opex estimates from `factors.py`; no detailed financing, NPV,
  degradation, or tariff time-of-use modelling.
- The roadmap search is a documented greedy under the energy hierarchy, not a
  full multi-objective optimiser.
- **Do not** treat this MVP as equivalent to ETAP / AVEVA / Resource Advisor.
