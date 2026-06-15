"""Command-line entry point for the Decarbonization Engineer.

Examples:
  python -m decarb.cli run --scenario data/demo_office.json
  python -m decarb.cli run --scenario data/demo_office.json --live
  python -m decarb.cli run --scenario data/demo_office.json --approve --reviewer "A. Expert"
  python -m decarb.cli run --scenario data/demo_office.json --out out/roadmap.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .agents import orchestrator
from .agents.base import is_live
from .models.ghg import GHGInventory
from .models.roadmap import Roadmap
from .storage import load_site, save_roadmap
from .validation import (
    ExpertDecision,
    ExpertStatus,
    Guardrails,
    apply_decision,
    evaluate,
    record_decision,
)


def _print_inventory(inv: GHGInventory, title: str) -> None:
    print(f"\n{title}")
    print(f"  Scope 1               : {inv.scope1_tco2e:10.1f} tCO2e")
    print(f"  Scope 2 (location)    : {inv.scope2_location_tco2e:10.1f} tCO2e")
    print(f"  Scope 2 (market)      : {inv.scope2_market_tco2e:10.1f} tCO2e")
    print(f"  Scope 3 (manual)      : {inv.scope3_tco2e:10.1f} tCO2e")
    print(f"  Operational (S1+S2mkt): {inv.operational_market:10.1f} tCO2e")
    print(f"  Total (market + S3)   : {inv.total_market_based:10.1f} tCO2e")


def _print_roadmap(rm: Roadmap) -> None:
    print("\n" + "=" * 78)
    print(f"  DECARBONIZATION ROADMAP  -  {rm.site_name}")
    print(f"  Horizon {rm.base_year}->{rm.target_year}   |   proposals: {rm.generated_with}")
    print("=" * 78)

    _print_inventory(rm.baseline_inventory, "Baseline inventory:")
    _print_inventory(rm.final_inventory, f"Final inventory ({rm.target_year}):")

    print(f"\n  -> {rm.pct_to_net_zero:.1f}% to net-zero (operational, market-based)")
    print(f"  -> {rm.operational_reduction_tco2e:,.1f} tCO2e/yr operational reduction")
    print(f"  -> Total capex ${rm.total_capex:,.0f}")
    print(f"  -> Residual location-based operational: "
          f"{rm.final_inventory.operational_location:,.1f} tCO2e (physical grid dependence)")

    print("\n  Selected measures:")
    print(f"  {'Yr':>4} {'Pillar':10} {'Measure':42} {'Capex':>12} {'tCO2e/yr':>9} {'$/tCO2e':>9}")
    print("  " + "-" * 90)
    for m in rm.measures:
        cpt = "n/a" if m.cost_per_tco2e == float("inf") else f"{m.cost_per_tco2e:,.0f}"
        print(f"  {m.year!s:>4} {m.pillar.value:10} {m.name[:42]:42} "
              f"{m.capex:>12,.0f} {m.tco2e_delta:>9.1f} {cpt:>9}")

    print("\n  Path to net-zero (operational, market-based):")
    for ys in rm.yearly:
        bar = "#" * int(round(ys.pct_reduction_vs_baseline / 4))
        print(f"    {ys.year}  {ys.pct_reduction_vs_baseline:5.1f}%  "
              f"gap {ys.gap_to_net_zero_tco2e:7.1f} t  {bar}")

    print("\n  Cost / carbon frontier (real, location-based abatement):")
    for p in rm.pareto:
        print(f"    ${p.capex:>11,.0f}  ->  {p.tco2e_reduction:7.1f} tCO2e/yr  "
              f"({p.measure_count} measures)")


def _run(args: argparse.Namespace) -> int:
    site = load_site(args.scenario)

    live = None
    if args.live:
        if not is_live():
            print("[warn] --live requested but no ANTHROPIC_API_KEY / SDK available; "
                  "falling back to offline proposals.", file=sys.stderr)
        live = True
    elif args.offline:
        live = False

    roadmap = orchestrator.run(site, live=live)
    _print_roadmap(roadmap)

    # --- Expert gate (mandatory) -------------------------------------------
    guardrails = Guardrails.from_site(site)
    if args.min_pct is not None:
        guardrails.min_pct_to_net_zero = args.min_pct
    violations = evaluate(roadmap, guardrails)

    print("\n" + "-" * 78)
    print("  EXPERT VALIDATION GATE")
    print("-" * 78)
    if violations:
        print("  Guardrail violations:")
        for v in violations:
            print(f"    [{v.code}] {v.message}")
    else:
        print("  No guardrail violations against default guardrails.")

    flagged = [(m.name, m.flags) for m in roadmap.measures if m.flags]
    if flagged:
        print("  Measure flags for review:")
        for name, flags in flagged:
            print(f"    - {name}: {'; '.join(flags)}")

    decision_status = None
    if args.approve:
        decision_status = ExpertStatus.APPROVED
    elif args.reject:
        decision_status = ExpertStatus.REJECTED

    if decision_status is None:
        print("\n  STATUS: PENDING - no expert decision supplied.")
        print("  Nothing is deployed. Re-run with --approve or --reject "
              "(and --reviewer NAME), or use the Streamlit app.")
    else:
        decision = ExpertDecision(status=decision_status, reviewer=args.reviewer,
                                  notes=args.notes or "")
        roadmap = apply_decision(roadmap, site, decision)
        entry = record_decision(roadmap, decision, guardrails, violations,
                                log_path=args.log)
        print(f"\n  STATUS: {decision.status.value.upper()} by {decision.reviewer} "
              f"at {decision.timestamp}")
        print(f"  Logged to {args.log}")

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        save_roadmap(roadmap, args.out)
        print(f"\n  Roadmap saved to {args.out}")

    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="decarb", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("run", help="Run the decarbonization engine on a scenario.")
    r.add_argument("--scenario", required=True, help="Path to a SiteProfile JSON.")
    mode = r.add_mutually_exclusive_group()
    mode.add_argument("--live", action="store_true", help="Use live LLM agents.")
    mode.add_argument("--offline", action="store_true", help="Force offline proposals.")
    r.add_argument("--min-pct", dest="min_pct", type=float, default=None,
                   help="Guardrail: minimum %% to net-zero required.")
    decision = r.add_mutually_exclusive_group()
    decision.add_argument("--approve", action="store_true", help="Expert approves the roadmap.")
    decision.add_argument("--reject", action="store_true", help="Expert rejects the roadmap.")
    r.add_argument("--reviewer", default="unknown", help="Expert name for the log.")
    r.add_argument("--notes", default="", help="Expert notes for the log.")
    r.add_argument("--log", default="decision_log.json", help="Decision log path.")
    r.add_argument("--out", default=None, help="Save the roadmap JSON here.")
    r.set_defaults(func=_run)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
