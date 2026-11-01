"""Unit and integration tests for the organisation-evolution simulator."""

from __future__ import annotations

import json
import unittest

from orgsim.config import baseline_config
from orgsim.scenarios import build_config, run_experiment, run_scenario
from orgsim.simulation import Simulation


class SimulationTests(unittest.TestCase):
    def make_sim(self, *, steps=35, population=180, seed=5, **overrides) -> Simulation:
        cfg = baseline_config(
            steps=steps,
            population=population,
            initial_firms=max(4, population // 30),
            seed=seed,
            **overrides,
        )
        return Simulation(cfg)

    def test_identical_seeds_are_reproducible(self):
        a = self.make_sim(seed=9)
        b = self.make_sim(seed=9)
        a.run()
        b.run()
        keys = (
            "weighted_height",
            "weighted_manager_ratio",
            "output_per_worker",
            "employed",
            "firms",
        )
        for key in keys:
            self.assertAlmostEqual(a.summarize()[key], b.summarize()[key], places=6)

    def test_firm_tree_is_internally_consistent(self):
        sim = self.make_sim(steps=45, population=240, seed=12)
        sim.run()
        self.assertTrue(sim.alive_firms)
        for firm in sim.alive_firms:
            self.assertIn(firm.ceo_id, firm.employees)
            self.assertIsNone(firm.manager[firm.ceo_id])
            # Every non-root has a valid parent, and appears in that parent's
            # child list.  The reverse is also true: no orphaned child pointers.
            for agent_id in firm.employees:
                if agent_id != firm.ceo_id:
                    parent = firm.manager[agent_id]
                    self.assertIn(parent, firm.employees)
                    self.assertIn(agent_id, firm.children[parent])
                for child in firm.children.get(agent_id, []):
                    self.assertIn(child, firm.employees)
                    self.assertEqual(firm.manager[child], agent_id)
                    self.assertEqual(firm.level[child], firm.level[agent_id] + 1)
            self.assertEqual(firm.height, max(firm.level.values()) + 1)
            self.assertGreaterEqual(firm.manager_ratio, 0.0)
            self.assertLessEqual(firm.manager_ratio, 1.0)

    def test_no_ladder_counterfactual_has_no_wage_subsidy(self):
        sim = self.make_sim(
            steps=30,
            population=200,
            seed=4,
            career_ladder_weight=0.0,
            retention_promotions=False,
        )
        sim.run()
        self.assertEqual(sim.summarize()["career_discount"], 0.0)
        self.assertEqual(sum(row["retention_promotions"] for row in sim.history), 0)
        self.assertTrue(all(agent.career_discount == 0.0 for agent in sim.agents.values()))

    def test_retention_promotions_occur_when_enabled(self):
        sim = self.make_sim(
            steps=55,
            population=260,
            seed=3,
            retention_promotions=True,
            retention_promotion_rate=0.55,
        )
        sim.run()
        total = sum(row["retention_promotions"] for row in sim.history)
        self.assertGreater(total, 0)

    def test_ceo_departure_repairs_tree(self):
        sim = self.make_sim(steps=1, population=60, seed=8)
        firm = next(f for f in sim.alive_firms if len(f.children.get(f.ceo_id, [])) >= 2)
        old_ceo = firm.ceo_id
        reports = list(firm.children[old_ceo])
        old_ceo_agent = sim.agents[old_ceo]
        sim.agents[old_ceo].firm_id = None
        firm.remove_employee(old_ceo, sim.rng)
        self.assertTrue(firm.alive)
        self.assertNotEqual(firm.ceo_id, old_ceo)
        self.assertIn(firm.ceo_id, firm.employees)
        self.assertIsNone(firm.manager[firm.ceo_id])
        for report in reports:
            if report == firm.ceo_id:
                continue
            self.assertEqual(firm.manager[report], firm.ceo_id)
            self.assertIn(report, firm.children[firm.ceo_id])
        self.assertEqual(sim.agents[old_ceo].firm_id, None)
        self.assertNotEqual(old_ceo_agent.firm_id, firm.id)

    def test_result_is_json_serialisable(self):
        sim = self.make_sim(steps=12, population=100, seed=2)
        sim.run()
        payload = sim.to_dict(include_trees=True, include_history=True)
        encoded = json.dumps(payload)
        self.assertGreater(len(encoded), 1000)
        self.assertIn("history", payload)
        self.assertIn("trees", payload)

    def test_scenario_experiment_has_hypothesis_block(self):
        exp = run_experiment(
            ("baseline", "no_ladder"),
            seeds=(3,),
            steps=28,
            population=120,
        )
        self.assertIn("hypothesis", exp)
        self.assertIn(exp["hypothesis"]["verdict"], {"supported", "partial", "not_supported"})
        self.assertEqual(exp["aggregates"]["no_ladder"]["career_discount"]["mean"], 0.0)


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from orgsim.web import create_app
        except ImportError as exc:  # pragma: no cover
            raise unittest.SkipTest(f"Flask is not available: {exc}")
        cls.app = create_app()
        cls.client = cls.app.test_client()

    def test_index_and_scenarios(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        response = self.client.get("/api/scenarios")
        self.assertEqual(response.status_code, 200)
        keys = {row["key"] for row in response.get_json()["scenarios"]}
        self.assertIn("baseline", keys)
        self.assertIn("no_ladder", keys)

    def test_run_endpoint(self):
        response = self.client.post(
            "/api/run",
            json={"scenario": "baseline", "steps": 18, "population": 120, "seed": 2},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["meta"]["scenario"], "baseline")
        self.assertIn("summary", payload)
        self.assertTrue(payload["trees"])

    def test_bad_scenario_is_rejected(self):
        response = self.client.post(
            "/api/run",
            json={"scenario": "not_a_scenario", "steps": 20, "population": 120},
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
