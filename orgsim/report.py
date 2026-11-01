"""Plain-text and file reporting for simulation runs and experiments."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .scenarios import comparison_rows


def _fmt(value: float, digits: int = 1) -> str:
    return f"{value:,.{digits}f}"


def format_run(result: dict[str, Any]) -> str:
    meta = result["meta"]
    summary = result["summary"]
    config = result["config"]
    lines: list[str] = []
    lines.append("ORG EVOLUTION / RUN REPORT")
    lines.append("=" * 78)
    lines.append(f"Scenario      : {meta['scenario']} — {meta['description']}")
    lines.append(
        f"Seed / steps  : {meta['seed']} / {meta['steps']}    "
        f"Population: {meta['population']}"
    )
    lines.append(
        f"Career weight : {config['career_ladder_weight']:.2f}    "
        f"Competition: {config['competition']:.2f}"
    )
    lines.append("")
    lines.append("FINAL-WINDOW OUTCOMES (last quarter of the run)")
    lines.append("-" * 78)
    rows = [
        ("Employed workers (avg)", _fmt(summary.get("employed", 0), 0)),
        ("Live firms (avg)", _fmt(summary.get("firms", 0), 1)),
        ("Average firm size", _fmt(summary.get("avg_firm_size", 0), 1)),
        ("Largest firm", _fmt(summary.get("max_firm_size", 0), 1)),
        ("Employment-weighted height", _fmt(summary.get("weighted_height", 0), 2)),
        ("Employment-weighted manager ratio", f"{summary.get('weighted_manager_ratio', 0):.1%}"),
        ("Output per worker", _fmt(summary.get("output_per_worker", 0), 1)),
        ("Wage per worker", _fmt(summary.get("wage_per_worker", 0), 1)),
        ("Profit margin", f"{summary.get('profit_margin', 0):.1%}"),
        ("Ladder wage discount", f"{summary.get('career_discount', 0):.1%}"),
        ("Tall-firm employment share", f"{summary.get('tall_employment_share', 0):.1%}"),
        ("Survival rate", f"{summary.get('survival_rate', 0):.1%}"),
        ("Total entries / exits", f"{summary.get('total_entries', 0):.0f} / {summary.get('total_exits', 0):.0f}"),
        ("Promotions / retention promotions", f"{summary.get('promotions', 0):.2f} / {summary.get('retention_promotions', 0):.2f} per step"),
    ]
    for label, value in rows:
        lines.append(f"  {label:<38s} {value:>18s}")
    lines.append("")
    lines.append("LARGEST LIVE FIRMS")
    lines.append("-" * 78)
    lines.append(
        f"  {'Firm':<22s} {'Size':>5s} {'H':>3s} {'Mgr%':>6s} {'Out/worker':>10s} {'Profit':>10s} {'Span':>5s}"
    )
    for firm in result.get("firms", [])[:10]:
        lines.append(
            f"  {firm['name'][:22]:<22s} {firm['headcount']:>5d} {firm['height']:>3d} "
            f"{firm['manager_ratio'] * 100:>5.1f}% {firm['output_per_worker']:>10.1f} "
            f"{firm['profit']:>10.0f} {firm['span_target']:>5d}"
        )
    if not result.get("firms"):
        lines.append("  (no live firms)")
    lines.append("")
    lines.append("INTERPRETATION")
    lines.append("-" * 78)
    lines.append(
        "Height is the number of levels in a firm. Manager ratio is the share of\n"
        "employees with direct reports. Ladder wage discount is the average share\n"
        "of pay workers give up for perceived promotion prospects. Use the\n"
        "experiment command or the web UI to compare this run with the no-ladder\n"
        "counterfactual; one run alone is not evidence for the hypothesis."
    )
    return "\n".join(lines)


def format_experiment(exp: dict[str, Any]) -> str:
    lines: list[str] = []
    meta = exp["meta"]
    lines.append("ORG EVOLUTION / EXPERIMENT REPORT")
    lines.append("=" * 96)
    lines.append(
        f"Seeds: {', '.join(str(s) for s in meta['seeds'])}    "
        f"Steps: {meta['steps']}    Population: {meta['population']}"
    )
    lines.append("")
    header = (
        f"{'Scenario':<27s} {'Height':>7s} {'Mgr%':>7s} {'Out/head':>9s} "
        f"{'Wage':>7s} {'Margin':>7s} {'Size':>7s} {'Employed':>9s} {'Survive':>8s} {'Discount':>8s}"
    )
    lines.append(header)
    lines.append("-" * len(header))
    for row in comparison_rows(exp):
        lines.append(
            f"{row['scenario']:<27s} {row['height']:>7.2f} "
            f"{row['manager_ratio'] * 100:>6.1f}% {row['output_per_worker']:>9.1f} "
            f"{row['wage_per_worker']:>7.1f} {row['profit_margin'] * 100:>6.1f}% "
            f"{row['avg_firm_size']:>7.1f} {row['employed']:>9.1f} "
            f"{row['survival_rate'] * 100:>7.1f}% {row['career_discount'] * 100:>7.1f}%"
        )
    lines.append("")
    hypothesis = exp.get("hypothesis")
    if hypothesis:
        lines.append("HYPOTHESIS TEST: baseline vs no-ladder")
        lines.append("-" * 96)
        lines.append(f"Verdict: {hypothesis['verdict'].upper()} — {hypothesis['headline']}")
        deltas = hypothesis["deltas"]
        lines.append("")
        lines.append(f"  Height delta (baseline - no ladder)       : {deltas['height']:+.2f} levels")
        lines.append(f"  Manager-ratio delta                       : {deltas['manager_ratio']:+.1%}")
        lines.append(f"  Output/worker delta                       : {deltas['productivity']:+.2f}")
        lines.append(f"  Wage delta                                : {deltas['wage']:+.2f}")
        lines.append(f"  Average firm-size delta                   : {deltas['size']:+.2f}")
        lines.append(f"  Employment delta                          : {deltas['employment']:+.1f}")
        lines.append(f"  Survival-rate delta                       : {deltas['survival']:+.1%}")
        lines.append(f"  Profit-margin delta                       : {deltas['profit_margin']:+.1%}")
        lines.append("")
        lines.append("  Conditions:")
        for name, passed in hypothesis["conditions"].items():
            lines.append(f"    [{'PASS' if passed else 'FAIL'}] {name.replace('_', ' ')}")
        consistent = hypothesis["consistent_seed_directions"]
        n = len(hypothesis["paired_seeds"])
        lines.append(
            "  Paired seeds: "
            f"{consistent['taller']}/{n} taller, "
            f"{consistent['less_productive']}/{n} less productive, "
            f"{consistent['not_smaller']}/{n} not smaller."
        )
        lines.append("  " + hypothesis["note"])
        lines.append("")
    competition = exp.get("competition")
    if competition:
        lines.append("COMPETITION CHECK")
        lines.append("-" * 96)
        lines.append(
            "  Sheltered minus baseline height: "
            f"{competition['sheltered_minus_baseline_height']:+.2f}; "
            "high-competition minus baseline height: "
            f"{competition['high_minus_baseline_height']:+.2f}"
        )
        lines.append(
            "  Baseline minus sheltered profit margin: "
            f"{competition['baseline_minus_sheltered_margin']:+.1%}; "
            "high-competition minus baseline margin: "
            f"{competition['high_minus_baseline_margin']:+.1%}"
        )
        lines.append(
            "  Baseline minus sheltered survival: "
            f"{competition['baseline_minus_sheltered_survival']:+.1%}; "
            "high-competition minus baseline survival: "
            f"{competition['high_minus_baseline_survival']:+.1%}"
        )
        lines.append("")
    lines.append("CAVEAT")
    lines.append("-" * 96)
    lines.append(
        "These are effect sizes from a deliberately stylised model, not estimates\n"
        "from real organisations. The useful output is the direction and robustness\n"
        "of the mechanism under parameter changes, not the absolute numbers."
    )
    return "\n".join(lines)


def write_json(data: dict[str, Any], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def write_csv(exp: dict[str, Any], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = comparison_rows(exp)
    if not rows:
        path.write_text("", encoding="utf-8")
        return path
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path
