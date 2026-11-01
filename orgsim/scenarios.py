"""Named scenarios and reproducible experiment aggregation."""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any, Iterable

from .config import Config, baseline_config
from .simulation import Simulation


@dataclass(frozen=True)
class Scenario:
    key: str
    label: str
    description: str
    overrides: dict[str, Any] = field(default_factory=dict)


SCENARIOS: dict[str, Scenario] = {
    "baseline": Scenario(
        key="baseline",
        label="Career ladder + competition",
        description=(
            "Workers value promotion prospects, firms use retention promotions, "
            "and output markets are competitive."
        ),
        overrides={},
    ),
    "no_ladder": Scenario(
        key="no_ladder",
        label="No career-ladder preference",
        description=(
            "Identical economy, but workers place no value on promotion prospects "
            "and will not trade wages for a ladder. Retention promotions are off."
        ),
        overrides={
            "career_ladder_weight": 0.0,
            "retention_promotions": False,
        },
    ),
    "no_competition": Scenario(
        key="no_competition",
        label="Sheltered market",
        description=(
            "Fixed output price and very little firm failure. Inefficient "
            "hierarchies are allowed to persist."
        ),
        overrides={
            "competition": 0.0,
            "entry_rate": 0.025,
            "failure_cash": -1.0e12,
            "base_price": 1.0,
        },
    ),
    "high_competition": Scenario(
        key="high_competition",
        label="High competitive pressure",
        description=(
            "A more contested output market, lower prices, easier entry, and a "
            "tighter failure threshold."
        ),
        overrides={
            "competition": 1.20,
            "base_price": 0.88,
            "entry_rate": 0.10,
            "failure_cash": -130.0,
            "max_firms": 28,
        },
    ),
    "career_no_retention": Scenario(
        key="career_no_retention",
        label="Career preference, no retention promotions",
        description=(
            "Workers still value career ladders, but firms do not create "
            "extra promotion slots to retain them. This isolates the retention "
            "channel from the compensating-differentials channel."
        ),
        overrides={"retention_promotions": False},
    ),
}


def build_config(
    scenario: str = "baseline",
    *,
    seed: int = 42,
    steps: int = 140,
    population: int = 420,
    **overrides: Any,
) -> Config:
    if scenario not in SCENARIOS:
        raise KeyError(f"Unknown scenario {scenario!r}. Choose from {sorted(SCENARIOS)}")
    spec = SCENARIOS[scenario]
    kwargs: dict[str, Any] = {
        "seed": seed,
        "steps": steps,
        "population": population,
        "scenario_name": spec.key,
        "scenario_description": spec.description,
    }
    kwargs.update(spec.overrides)
    kwargs.update(overrides)
    return baseline_config(**kwargs)


def run_scenario(
    scenario: str = "baseline",
    *,
    seed: int = 42,
    steps: int = 140,
    population: int = 420,
    include_trees: bool = True,
    include_history: bool = True,
    **overrides: Any,
) -> dict[str, Any]:
    cfg = build_config(
        scenario, seed=seed, steps=steps, population=population, **overrides
    )
    sim = Simulation(cfg)
    sim.run()
    return sim.to_dict(
        include_trees=include_trees, include_history=include_history
    )


METRICS = [
    "weighted_height",
    "weighted_manager_ratio",
    "output_per_worker",
    "wage_per_worker",
    "profit_margin",
    "avg_firm_size",
    "max_firm_size",
    "employed",
    "tall_employment_share",
    "career_discount",
    "promotion_prospect",
    "survival_rate",
    "total_entries",
    "total_exits",
    "voluntary_quits",
    "retention_promotions",
    "promotion_rate",
    "quit_rate",
]


def _run_summary(cfg: Config) -> dict[str, Any]:
    sim = Simulation(cfg)
    sim.run()
    summary = sim.summarize()
    summary["seed"] = cfg.seed
    summary["scenario"] = cfg.scenario_name
    return summary


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    out: dict[str, Any] = {"n": len(rows), "seeds": [r["seed"] for r in rows]}
    for key in METRICS:
        values = [float(r.get(key, 0.0)) for r in rows]
        out[key] = {
            "mean": round(statistics.fmean(values), 4),
            "sd": round(statistics.pstdev(values), 4) if len(values) > 1 else 0.0,
            "min": round(min(values), 4),
            "max": round(max(values), 4),
        }
    return out


def _mean(aggregate: dict[str, Any], key: str) -> float:
    value = aggregate.get(key, {})
    return float(value.get("mean", 0.0)) if isinstance(value, dict) else 0.0


def _hypothesis_test(
    baseline: dict[str, Any], no_ladder: dict[str, Any], per_seed: dict[str, list[dict[str, Any]]]
) -> dict[str, Any]:
    deltas = {
        "height": _mean(baseline, "weighted_height") - _mean(no_ladder, "weighted_height"),
        "manager_ratio": _mean(baseline, "weighted_manager_ratio")
        - _mean(no_ladder, "weighted_manager_ratio"),
        "productivity": _mean(baseline, "output_per_worker")
        - _mean(no_ladder, "output_per_worker"),
        "size": _mean(baseline, "avg_firm_size") - _mean(no_ladder, "avg_firm_size"),
        "employment": _mean(baseline, "employed") - _mean(no_ladder, "employed"),
        "survival": _mean(baseline, "survival_rate") - _mean(no_ladder, "survival_rate"),
        "wage": _mean(baseline, "wage_per_worker") - _mean(no_ladder, "wage_per_worker"),
        "profit_margin": _mean(baseline, "profit_margin")
        - _mean(no_ladder, "profit_margin"),
    }

    # Consistency across paired seeds is more informative than a single run.
    paired = []
    by_seed_base = {r["seed"]: r for r in per_seed.get("baseline", [])}
    by_seed_nolad = {r["seed"]: r for r in per_seed.get("no_ladder", [])}
    for seed in sorted(set(by_seed_base) & set(by_seed_nolad)):
        b, n = by_seed_base[seed], by_seed_nolad[seed]
        paired.append(
            {
                "seed": seed,
                "height_delta": round(
                    b["weighted_height"] - n["weighted_height"], 4
                ),
                "manager_ratio_delta": round(
                    b["weighted_manager_ratio"] - n["weighted_manager_ratio"], 4
                ),
                "productivity_delta": round(
                    b["output_per_worker"] - n["output_per_worker"], 4
                ),
                "employment_delta": round(b["employed"] - n["employed"], 4),
                "survival_delta": round(
                    b["survival_rate"] - n["survival_rate"], 4
                ),
            }
        )

    conditions = {
        "taller_hierarchy": deltas["height"] > 0.20 and deltas["manager_ratio"] > 0.012,
        "lower_productivity": deltas["productivity"] < -0.35,
        "not_much_smaller": deltas["size"] >= -0.50 and deltas["employment"] >= -5.0,
    }
    consistent = {
        "taller": sum(1 for row in paired if row["height_delta"] > 0),
        "less_productive": sum(1 for row in paired if row["productivity_delta"] < 0),
        "not_smaller": sum(1 for row in paired if row["employment_delta"] >= -5.0),
    }
    support_count = sum(conditions.values())
    if all(conditions.values()):
        verdict = "supported"
        headline = (
            "The baseline forms taller, less productive hierarchies that stay "
            "large; removing career-ladder preferences flattens them."
        )
    elif support_count >= 2:
        verdict = "partial"
        headline = (
            "The evidence points in the hypothesised direction, but at least one "
            "condition is weak or noisy."
        )
    else:
        verdict = "not_supported"
        headline = (
            "Career-ladder preferences do not clearly produce the predicted "
            "tall, unproductive, persistent hierarchies in this run."
        )
    return {
        "verdict": verdict,
        "headline": headline,
        "deltas": {key: round(value, 4) for key, value in deltas.items()},
        "conditions": conditions,
        "consistent_seed_directions": consistent,
        "paired_seeds": paired,
        "note": (
            "Deltas are baseline minus no-ladder. Positive height/manager deltas "
            "and negative productivity deltas support the mechanism; survival is "
            "reported separately because it measures market selection, not size. "
            "These are simulation effect sizes, not statistical significance tests."
        ),
    }


def _competition_test(
    baseline: dict[str, Any],
    sheltered: dict[str, Any],
    high: dict[str, Any],
) -> dict[str, Any]:
    return {
        "sheltered_minus_baseline_height": round(
            _mean(sheltered, "weighted_height") - _mean(baseline, "weighted_height"), 4
        ),
        "high_minus_baseline_height": round(
            _mean(high, "weighted_height") - _mean(baseline, "weighted_height"), 4
        ),
        "baseline_minus_sheltered_survival": round(
            _mean(baseline, "survival_rate") - _mean(sheltered, "survival_rate"), 4
        ),
        "high_minus_baseline_survival": round(
            _mean(high, "survival_rate") - _mean(baseline, "survival_rate"), 4
        ),
        "baseline_minus_sheltered_margin": round(
            _mean(baseline, "profit_margin") - _mean(sheltered, "profit_margin"), 4
        ),
        "high_minus_baseline_margin": round(
            _mean(high, "profit_margin") - _mean(baseline, "profit_margin"), 4
        ),
    }


def run_experiment(
    scenarios: Iterable[str] = ("baseline", "no_ladder", "no_competition", "high_competition"),
    *,
    seeds: Iterable[int] = (11, 23, 37),
    steps: int = 110,
    population: int = 400,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scenario_keys = list(scenarios)
    seed_list = list(seeds)
    unknown = [key for key in scenario_keys if key not in SCENARIOS]
    if unknown:
        raise KeyError(f"Unknown scenarios: {unknown}")
    overrides = overrides or {}
    per_seed: dict[str, list[dict[str, Any]]] = {}
    aggregates: dict[str, Any] = {}
    for key in scenario_keys:
        rows = []
        for seed in seed_list:
            cfg = build_config(
                key,
                seed=seed,
                steps=steps,
                population=population,
                **overrides,
            )
            rows.append(_run_summary(cfg))
        per_seed[key] = rows
        aggregates[key] = _aggregate(rows)

    hypothesis = None
    if "baseline" in aggregates and "no_ladder" in aggregates:
        hypothesis = _hypothesis_test(
            aggregates["baseline"], aggregates["no_ladder"], per_seed
        )
    competition = None
    if all(k in aggregates for k in ("baseline", "no_competition", "high_competition")):
        competition = _competition_test(
            aggregates["baseline"],
            aggregates["no_competition"],
            aggregates["high_competition"],
        )
    return {
        "meta": {
            "model": "orgsim",
            "version": "0.1.0",
            "steps": steps,
            "population": population,
            "seeds": seed_list,
            "scenarios": scenario_keys,
            "overrides": overrides,
        },
        "scenarios": {
            key: {
                "label": SCENARIOS[key].label,
                "description": SCENARIOS[key].description,
            }
            for key in scenario_keys
        },
        "aggregates": aggregates,
        "runs": per_seed,
        "hypothesis": hypothesis,
        "competition": competition,
    }


def comparison_rows(experiment: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten aggregates into rows suitable for a table or CSV."""
    rows = []
    for key, agg in experiment.get("aggregates", {}).items():
        rows.append(
            {
                "scenario": key,
                "label": experiment["scenarios"][key]["label"],
                "height": _mean(agg, "weighted_height"),
                "manager_ratio": _mean(agg, "weighted_manager_ratio"),
                "output_per_worker": _mean(agg, "output_per_worker"),
                "wage_per_worker": _mean(agg, "wage_per_worker"),
                "profit_margin": _mean(agg, "profit_margin"),
                "avg_firm_size": _mean(agg, "avg_firm_size"),
                "employed": _mean(agg, "employed"),
                "survival_rate": _mean(agg, "survival_rate"),
                "tall_employment_share": _mean(agg, "tall_employment_share"),
                "career_discount": _mean(agg, "career_discount"),
                "exits": _mean(agg, "total_exits"),
            }
        )
    return rows
