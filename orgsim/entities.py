"""Agents, behaviours, and the firm hierarchy data structure."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .config import FirmStrategy


class Behavior(str, Enum):
    OPERATOR = "operator"
    CAREERIST = "careerist"
    LOYALIST = "loyalist"
    POLITICIAN = "politician"
    STEADY = "steady"


# Mean shifts applied to the common trait distributions.  These are behavioural
# archetypes, not deterministic labels: an operator can still be ambitious.
BEHAVIOR_PROFILES = {
    Behavior.OPERATOR: {
        "label": "Operator",
        "weight": 0.26,
        "skill": 0.11,
        "ambition": -0.13,
        "support": -0.04,
        "mobility": 0.05,
        "politics": -0.12,
    },
    Behavior.CAREERIST: {
        "label": "Careerist",
        "weight": 0.22,
        "skill": 0.02,
        "ambition": 0.26,
        "support": 0.05,
        "mobility": 0.15,
        "politics": 0.05,
    },
    Behavior.LOYALIST: {
        "label": "Loyalist",
        "weight": 0.19,
        "skill": -0.01,
        "ambition": -0.04,
        "support": 0.31,
        "mobility": -0.20,
        "politics": 0.02,
    },
    Behavior.POLITICIAN: {
        "label": "Politician",
        "weight": 0.14,
        "skill": -0.09,
        "ambition": 0.15,
        "support": 0.29,
        "mobility": 0.04,
        "politics": 0.25,
    },
    Behavior.STEADY: {
        "label": "Steady",
        "weight": 0.19,
        "skill": 0.00,
        "ambition": -0.07,
        "support": 0.00,
        "mobility": -0.03,
        "politics": -0.01,
    },
}


@dataclass
class Agent:
    id: int
    name: str
    behavior: Behavior
    skill: float
    ambition: float
    hierarchy_support: float
    mobility: float
    politics: float

    firm_id: Optional[int] = None
    wage: float = 0.0
    career_discount: float = 0.0
    level: int = 0
    tenure: int = 0
    promotions: int = 0
    job_changes: int = 0
    employed_since: int = 0
    lifetime_earnings: float = 0.0

    @property
    def employed(self) -> bool:
        return self.firm_id is not None

    def promotion_score(self, meritocracy: float, rng) -> float:
        """Firms promote on a mix of merit and internal political support."""
        merit = self.skill
        politics = 0.58 * self.hierarchy_support + 0.27 * self.ambition + 0.15 * self.politics
        return (
            meritocracy * merit
            + (1.0 - meritocracy) * politics
            + rng.gauss(0.0, 0.055)
        )


@dataclass
class Firm:
    id: int
    name: str
    strategy: FirmStrategy
    founder_id: int
    cash: float
    age: int = 0
    alive: bool = True

    ceo_id: int = -1
    employees: set[int] = field(default_factory=set)
    manager: dict[int, Optional[int]] = field(default_factory=dict)
    children: dict[int, list[int]] = field(default_factory=dict)
    level: dict[int, int] = field(default_factory=dict)

    # Last-step accounting, retained for diagnostics and the UI.
    output: float = 0.0
    revenue: float = 0.0
    payroll: float = 0.0
    profit: float = 0.0
    output_per_worker: float = 0.0
    target_headcount: int = 0
    hires: int = 0
    quits: int = 0
    layoffs: int = 0
    promotions: int = 0
    retention_promotions: int = 0
    entry_step: int = 0
    _cached_height: int = 0
    _cached_manager_ratio: float = 0.0

    def __post_init__(self) -> None:
        if self.ceo_id < 0:
            self.ceo_id = self.founder_id

    # ------------------------------------------------------------------
    # Structure
    # ------------------------------------------------------------------
    @property
    def headcount(self) -> int:
        return len(self.employees)

    @property
    def height(self) -> int:
        return self._cached_height

    @property
    def manager_ratio(self) -> float:
        return self._cached_manager_ratio

    @property
    def managers(self) -> list[int]:
        return [a for a in self.employees if self.children.get(a)]

    @property
    def ic_employees(self) -> list[int]:
        return [a for a in self.employees if not self.children.get(a)]

    @property
    def average_span(self) -> float:
        managers = self.managers
        if not managers:
            return 0.0
        return sum(len(self.children[m]) for m in managers) / len(managers)

    def rebuild_levels(self) -> None:
        """Recompute levels by walking down from the CEO."""
        if self.ceo_id not in self.employees:
            self.level = {a: 0 for a in self.employees}
            self._cached_height = 1 if self.employees else 0
            self._cached_manager_ratio = 0.0
            return
        levels = {self.ceo_id: 0}
        queue = [self.ceo_id]
        while queue:
            parent = queue.pop(0)
            for child in self.children.get(parent, []):
                if child not in levels:
                    levels[child] = levels[parent] + 1
                    queue.append(child)
        # Defensive fallback for malformed trees: attach floating nodes at depth 1.
        for agent_id in self.employees:
            levels.setdefault(agent_id, 1 if agent_id != self.ceo_id else 0)
        self.level = levels
        self._cached_height = (max(levels.values()) + 1) if levels else 0
        manager_count = sum(1 for agent_id in self.employees if self.children.get(agent_id))
        self._cached_manager_ratio = (
            manager_count / len(self.employees) if self.employees else 0.0
        )

    def add_employee(
        self, agent_id: int, manager_id: Optional[int], level: int, wage: float
    ) -> None:
        self.employees.add(agent_id)
        self.manager[agent_id] = manager_id
        self.children.setdefault(agent_id, [])
        self.level[agent_id] = level
        if manager_id is not None:
            self.children.setdefault(manager_id, []).append(agent_id)
        self.rebuild_levels()

    def make_ceo(self, agent_id: int) -> None:
        self.employees.add(agent_id)
        self.ceo_id = agent_id
        self.manager[agent_id] = None
        self.children.setdefault(agent_id, [])
        self.rebuild_levels()

    def _best_successor(self, candidates: list[int], rng) -> Optional[int]:
        if not candidates:
            return None
        scored = []
        for aid in candidates:
            # Successors are chosen from direct reports; political support matters.
            scored.append((self.children.get(aid, []) and 0.015 or 0.0, aid))
        # Prefer managers with the largest teams, then let the simulation's
        # promotion score break ties.  A tiny random term avoids id collisions.
        return max(scored, key=lambda pair: (pair[0], -pair[1]))[1]

    def remove_employee(self, agent_id: int, rng) -> Optional[int]:
        """Remove an agent, repairing the tree.  Returns the new manager (if any)."""
        if agent_id not in self.employees:
            return None
        old_manager = self.manager.get(agent_id)
        reports = list(self.children.get(agent_id, []))

        if agent_id == self.ceo_id:
            self.employees.discard(agent_id)
            self.manager.pop(agent_id, None)
            self.children.pop(agent_id, None)
            self.level.pop(agent_id, None)
            if not reports:
                self.alive = False
                return None
            successor = self._best_successor(reports, rng)
            assert successor is not None
            self.ceo_id = successor
            self.manager[successor] = None
            # The other direct reports now report to the successor.
            for report in reports:
                if report == successor:
                    continue
                self.manager[report] = successor
                self.children.setdefault(successor, []).append(report)
            self.rebuild_levels()
            return None

        if old_manager is not None:
            siblings = self.children.get(old_manager, [])
            if agent_id in siblings:
                siblings.remove(agent_id)
        # Reports of a departing manager are reattached to its manager.  A later
        # capacity promotion can split an over-wide team.
        if old_manager is not None:
            for report in reports:
                self.manager[report] = old_manager
                self.children.setdefault(old_manager, []).append(report)
        self.employees.discard(agent_id)
        self.manager.pop(agent_id, None)
        self.children.pop(agent_id, None)
        self.level.pop(agent_id, None)
        if not self.employees:
            self.alive = False
        else:
            self.rebuild_levels()
        return old_manager

    def promote(self, agent_id: int, manager_id: int, rng) -> bool:
        """Promote an IC into a people-management role under ``manager_id``.

        A promotion is implemented as a team split: the new manager takes a
        couple of siblings with them.  Without reports the promotion would not
        change the hierarchy, so teams of at least two ICs are required.
        """
        if agent_id not in self.employees or agent_id == self.ceo_id:
            return False
        if self.children.get(agent_id):
            return False
        if self.manager.get(agent_id) != manager_id:
            return False

        siblings = [
            a
            for a in self.children.get(manager_id, [])
            if a != agent_id and not self.children.get(a)
        ]
        if not siblings:
            return False

        max_transfer = min(2, len(siblings))
        transfer = rng.randint(1, max_transfer)
        moved = rng.sample(siblings, transfer)
        for report in moved:
            self.children[manager_id].remove(report)
            self.manager[report] = agent_id
            self.children.setdefault(agent_id, []).append(report)
        self.level[agent_id] = self.level.get(manager_id, 0) + 1
        self.rebuild_levels()
        return True

    def capacity_manager(self, span: int) -> Optional[int]:
        """Return a manager with room, preferring the deepest available one."""
        candidates = [
            m
            for m in self.managers
            if len(self.children.get(m, [])) < span
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda m: (self.level.get(m, 0), -len(self.children[m])))

    def full_manager(self) -> Optional[int]:
        candidates = [
            m
            for m in self.managers
            if len(self.children.get(m, [])) >= max(2, self.strategy.span)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda m: len(self.children[m]))

    def promotion_candidate(self, manager_id: int, rng) -> Optional[int]:
        ics = [
            a
            for a in self.children.get(manager_id, [])
            if not self.children.get(a)
        ]
        if len(ics) < 2:
            return None
        return max(ics, key=lambda a: self._promotion_key(a, rng))

    def _promotion_key(self, agent_id: int, rng) -> float:
        # The firm object does not own agents, so this lightweight key is only a
        # fallback.  Simulation supplies the full behavioural score.
        return float(agent_id % 17) / 17.0 + rng.random() * 0.1

    # ------------------------------------------------------------------
    # Economics and promotion prospects
    # ------------------------------------------------------------------
    def compute_economics(self, price: float, fixed_cost: float) -> None:
        headcount = self.headcount
        if headcount == 0:
            self.output = self.revenue = self.payroll = self.profit = 0.0
            self.output_per_worker = 0.0
            return

        managers = self.managers
        ics = self.ic_employees
        manager_ratio = len(managers) / headcount
        height = self.height
        avg_span = self.average_span

        # Agents' skills are stored by the simulation in ``self._skill_cache``.
        skills: dict[int, float] = getattr(self, "_skill_cache", {})
        ic_skill = sum(skills.get(a, 0.5) for a in ics)
        manager_skill = sum(skills.get(a, 0.5) for a in managers)
        avg_manager_skill = manager_skill / max(1, len(managers))

        quality = 0.95 + 0.10 * self.strategy.quality
        scale = (headcount / 6.0) ** 0.045
        coordination_gain = 0.10 * min(1.15, avg_span / 5.0) * avg_manager_skill
        bureaucracy_drag = (
            0.035 * max(0, height - 2)
            + 0.50 * max(0, manager_ratio - 0.22)
            + 0.20 * max(0, 0.08 - manager_ratio)
        )
        effective = max(0.25, 1.0 + coordination_gain - bureaucracy_drag)
        self.output = (
            (ic_skill + 0.55 * manager_skill)
            * effective
            * scale
            * quality
            * 100.0
        )
        self.revenue = self.output * price
        self.payroll = sum(getattr(self, "_wage_cache", {}).get(a, 0.0) for a in self.employees)
        self.profit = self.revenue - self.payroll - fixed_cost
        self.output_per_worker = self.output / headcount

    def promotion_prospect(self, agent: Agent, open_slots: int = 0) -> float:
        """A worker's perceived chance of moving up, in [0.02, 0.65]."""
        if not self.employees:
            return 0.0
        open_ratio = min(1.0, max(0, open_slots) / max(1, self.headcount))
        manager_penalty = 0.35 * max(0.0, self.manager_ratio - 0.22)
        # Narrow spans mean more managerial rungs per head, which workers can
        # actually aspire to.  This is distinct from raw headcount growth.
        span_bonus = 0.12 * ((6.0 - self.strategy.span) / 4.0)
        prospect = (
            0.025
            + 0.060 * self.height
            + 0.22 * open_ratio
            + span_bonus
            + 0.018 * max(0, self.promotions)
            - manager_penalty
        )
        # Very junior workers see a little more room than people already high up.
        prospect *= 1.0 - 0.035 * agent.level
        return min(0.65, max(0.02, prospect))

    def choose_retention_candidate(self, rng) -> tuple[Optional[int], Optional[int]]:
        """Pick an ambitious IC in a team large enough to split."""
        options: list[tuple[float, int, int]] = []
        for manager_id in self.managers:
            ics = [
                a
                for a in self.children.get(manager_id, [])
                if not self.children.get(a)
            ]
            if len(ics) < max(2, self.strategy.span - 1):
                continue
            for aid in ics:
                options.append((rng.random(), manager_id, aid))
        if not options:
            return None, None
        _, manager_id, agent_id = max(options, key=lambda row: row[0])
        return manager_id, agent_id

    # ------------------------------------------------------------------
    # Snapshot helpers
    # ------------------------------------------------------------------
    def snapshot(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "headcount": self.headcount,
            "height": self.height,
            "manager_ratio": round(self.manager_ratio, 4),
            "average_span": round(self.average_span, 2),
            "output": round(self.output, 1),
            "revenue": round(self.revenue, 1),
            "payroll": round(self.payroll, 1),
            "profit": round(self.profit, 1),
            "cash": round(self.cash, 1),
            "output_per_worker": round(self.output_per_worker, 2),
            "age": self.age,
            "span_target": self.strategy.span,
            "wage_offer": round(self.strategy.wage_offer, 3),
            "meritocracy": round(self.strategy.meritocracy, 3),
            "entry_step": self.entry_step,
            "hires": self.hires,
            "quits": self.quits,
            "promotions": self.promotions,
            "retention_promotions": self.retention_promotions,
        }

    def tree_snapshot(self, agents: dict[int, Agent]) -> dict:
        nodes = []
        for aid in self.employees:
            agent = agents[aid]
            nodes.append(
                {
                    "id": aid,
                    "name": agent.name,
                    "manager_id": self.manager.get(aid),
                    "level": self.level.get(aid, 0),
                    "behavior": agent.behavior.value,
                    "skill": round(agent.skill, 3),
                    "ambition": round(agent.ambition, 3),
                    "support": round(agent.hierarchy_support, 3),
                    "wage": round(agent.wage, 1),
                    "tenure": agent.tenure,
                    "promotions": agent.promotions,
                    "reports": len(self.children.get(aid, [])),
                }
            )
        nodes.sort(key=lambda node: (node["level"], node["id"]))
        return {
            "id": self.id,
            "name": self.name,
            "ceo_id": self.ceo_id,
            "height": self.height,
            "headcount": self.headcount,
            "manager_ratio": round(self.manager_ratio, 4),
            "output_per_worker": round(self.output_per_worker, 2),
            "span_target": self.strategy.span,
            "nodes": nodes,
        }
