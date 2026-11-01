"""Command-line interface for the organisation-evolution simulator."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .report import format_experiment, format_run, write_csv, write_json
from .scenarios import SCENARIOS, run_experiment, run_scenario

DEFAULT_SCENARIOS = ("baseline", "no_ladder", "no_competition", "high_competition")


def _parse_csv_ints(value: str) -> list[int]:
    return [int(part.strip()) for part in value.split(",") if part.strip()]


def _parse_csv_strings(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _parse_set(values: list[str] | None) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    for raw in values or []:
        if "=" not in raw:
            raise SystemExit(f"--set expects key=value, got {raw!r}")
        key, value = raw.split("=", 1)
        key, value = key.strip(), value.strip()
        if value.lower() in {"true", "false"}:
            parsed: Any = value.lower() == "true"
        else:
            try:
                parsed = int(value)
            except ValueError:
                try:
                    parsed = float(value)
                except ValueError:
                    parsed = value
        overrides[key] = parsed
    return overrides


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="orgsim",
        description=(
            "Agent-based simulator for the formation and evolution of hierarchies. "
            "Workers have different skills, ambitions, hierarchy support, and mobility; "
            "firms grow, promote, hire, and fail."
        ),
    )
    parser.add_argument("--version", action="version", version=f"orgsim {__version__}")
    sub = parser.add_subparsers(dest="command")

    run = sub.add_parser("run", help="run one scenario and print a report")
    run.add_argument("--scenario", default="baseline", choices=sorted(SCENARIOS))
    run.add_argument("--steps", type=int, default=140)
    run.add_argument("--population", type=int, default=420)
    run.add_argument("--seed", type=int, default=42)
    run.add_argument("--json", type=Path, help="write the complete result as JSON")
    run.add_argument("--set", action="append", help="override a config field, e.g. --set competition=0.2")

    exp = sub.add_parser("experiment", help="compare scenarios across seeds")
    exp.add_argument(
        "--scenarios",
        default=",".join(DEFAULT_SCENARIOS),
        help="comma-separated scenario keys",
    )
    exp.add_argument("--seeds", default="11,23,37", help="comma-separated integer seeds")
    exp.add_argument("--steps", type=int, default=100)
    exp.add_argument("--population", type=int, default=360)
    exp.add_argument("--json", type=Path, default=Path("results/experiment.json"))
    exp.add_argument("--csv", type=Path, default=Path("results/summary.csv"))
    exp.add_argument("--set", action="append", help="override a config field for every scenario")

    demo = sub.add_parser("demo", help="quick two-scenario demonstration")
    demo.add_argument("--steps", type=int, default=90)
    demo.add_argument("--population", type=int, default=320)
    demo.add_argument("--seeds", default="11,23")

    web = sub.add_parser("web", help="launch the local interactive web UI")
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", type=int, default=5050)
    web.add_argument("--debug", action="store_true")

    sub.add_parser("list", help="list scenarios")

    # If no subcommand is given, run the quick demo rather than dumping help.
    parser.set_defaults(command="demo", steps=90, population=320, seeds="11,23")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    command = getattr(args, "command", "demo")

    if command == "list":
        print("Available scenarios:\n")
        for key, spec in SCENARIOS.items():
            print(f"  {key:<22s} {spec.label}")
            print(f"  {'':<22s} {spec.description}\n")
        return 0

    if command == "run":
        overrides = _parse_set(getattr(args, "set", None))
        result = run_scenario(
            args.scenario,
            seed=args.seed,
            steps=args.steps,
            population=args.population,
            include_trees=True,
            include_history=True,
            **overrides,
        )
        print(format_run(result))
        if args.json:
            path = write_json(result, args.json)
            print(f"\nSaved full result to {path}")
        return 0

    if command == "experiment":
        scenarios = _parse_csv_strings(args.scenarios)
        unknown = [s for s in scenarios if s not in SCENARIOS]
        if unknown:
            parser.error(f"unknown scenarios: {unknown}; use `orgsim list`")
        overrides = _parse_set(getattr(args, "set", None))
        print(
            f"Running {len(scenarios)} scenarios x {len(_parse_csv_ints(args.seeds))} seeds "
            f"for {args.steps} steps ..."
        )
        experiment = run_experiment(
            scenarios,
            seeds=_parse_csv_ints(args.seeds),
            steps=args.steps,
            population=args.population,
            overrides=overrides,
        )
        print(format_experiment(experiment))
        json_path = write_json(experiment, args.json)
        csv_path = write_csv(experiment, args.csv)
        print(f"\nSaved experiment JSON to {json_path}")
        print(f"Saved comparison CSV to {csv_path}")
        return 0

    if command == "demo":
        scenarios = ("baseline", "no_ladder")
        experiment = run_experiment(
            scenarios,
            seeds=_parse_csv_ints(args.seeds),
            steps=args.steps,
            population=args.population,
        )
        print(format_experiment(experiment))
        print(
            "\nNext: `python run.py experiment` for the full comparison, or "
            "`python run.py web` for the interactive UI."
        )
        return 0

    if command == "web":
        try:
            from .web import create_app
        except ImportError as exc:
            print(
                "The web UI needs Flask. Install it with `python -m pip install flask`.",
                file=sys.stderr,
            )
            print(f"Import error: {exc}", file=sys.stderr)
            return 1
        app = create_app()
        print(f"Starting Ladder Lab at http://{args.host}:{args.port}")
        app.run(host=args.host, port=args.port, debug=args.debug)
        return 0

    parser.print_help()
    return 2
