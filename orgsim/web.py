"""Small Flask UI for exploring the simulation in a browser."""

from __future__ import annotations

from typing import Any

from flask import Flask, jsonify, render_template, request

from . import __version__
from .scenarios import SCENARIOS, run_experiment, run_scenario


def _int_payload(payload: dict[str, Any], key: str, default: int, low: int, high: int) -> int:
    try:
        value = int(payload.get(key, default))
    except (TypeError, ValueError):
        value = default
    return min(high, max(low, value))


def _float_payload(
    payload: dict[str, Any], key: str, default: float, low: float, high: float
) -> float:
    try:
        value = float(payload.get(key, default))
    except (TypeError, ValueError):
        value = default
    return min(high, max(low, value))


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False

    @app.get("/")
    def index() -> str:
        return render_template("index.html", version=__version__)

    @app.get("/api/scenarios")
    def scenarios() -> Any:
        return jsonify(
            {
                "scenarios": [
                    {
                        "key": key,
                        "label": spec.label,
                        "description": spec.description,
                        "overrides": spec.overrides,
                    }
                    for key, spec in SCENARIOS.items()
                ]
            }
        )

    @app.post("/api/run")
    def run() -> Any:
        payload = request.get_json(silent=True) or {}
        scenario = str(payload.get("scenario", "baseline"))
        if scenario not in SCENARIOS:
            return jsonify({"error": f"Unknown scenario {scenario!r}"}), 400
        steps = _int_payload(payload, "steps", 100, 20, 220)
        population = _int_payload(payload, "population", 360, 120, 650)
        seed = _int_payload(payload, "seed", 42, 0, 999_999)
        overrides: dict[str, Any] = {}
        if "career_ladder_weight" in payload:
            overrides["career_ladder_weight"] = _float_payload(
                payload, "career_ladder_weight", 1.0, 0.0, 1.5
            )
        try:
            result = run_scenario(
                scenario,
                seed=seed,
                steps=steps,
                population=population,
                include_trees=True,
                include_history=True,
                **overrides,
            )
            return jsonify(result)
        except Exception as exc:  # pragma: no cover - surfaced to the UI
            app.logger.exception("Simulation failed")
            return jsonify({"error": f"Simulation failed: {exc}"}), 500

    @app.post("/api/compare")
    def compare() -> Any:
        payload = request.get_json(silent=True) or {}
        steps = _int_payload(payload, "steps", 90, 30, 180)
        population = _int_payload(payload, "population", 360, 120, 550)
        seed = _int_payload(payload, "seed", 42, 0, 999_999)
        replicates = _int_payload(payload, "replicates", 2, 1, 3)
        seeds = [seed + i * 101 for i in range(replicates)]
        try:
            experiment = run_experiment(
                ("baseline", "no_ladder"),
                seeds=seeds,
                steps=steps,
                population=population,
            )
            return jsonify(experiment)
        except Exception as exc:  # pragma: no cover - surfaced to the UI
            app.logger.exception("Comparison failed")
            return jsonify({"error": f"Comparison failed: {exc}"}), 500

    @app.get("/api/health")
    def health() -> Any:
        return jsonify({"ok": True, "version": __version__})

    return app


app = create_app()
