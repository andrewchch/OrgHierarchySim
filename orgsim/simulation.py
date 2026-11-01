"""Agent-based simulation of firm formation, hierarchy, and labor-market sorting.

The model is intentionally small enough to reason about but rich enough for the
core hypothesis to fail.  Each step:

1. firms produce, set revenue, and pay wages;
2. weak firms shrink or die, strong firms set hiring targets;
3. firms promote for capacity and (if enabled) to retain ambitious workers;
4. vacancies are posted and workers move based on wages, promotion prospects,
   hierarchy affinity, and switching costs;
5. unemployed workers may found new firms, inheriting a mutated strategy.

The key comparative static is ``career_ladder_weight``.  When it is high,
workers accept lower wages at tall firms because promotion prospects are worth
something to them.  That wage discount can keep inefficient hierarchies alive.
"""

from __future__ import annotations

import math
import random
import statistics
from collections import Counter
from typing import Any, Optional

from .config import Config, FirmStrategy
from .entities import BEHAVIOR_PROFILES, Agent, Behavior, Firm

FIRST_NAMES = [
    "Ada", "Aiko", "Amara", "Anika", "Arjun", "Asha", "Beatriz", "Bruno",
    "Camila", "Chen", "Clara", "Dalia", "Darius", "Dev", "Elena", "Emeka",
    "Esha", "Farah", "Felix", "Freya", "Gabriel", "Hana", "Hugo", "Imani",
    "Iris", "Jonas", "Julia", "Kai", "Kiran", "Leila", "Leo", "Lucia",
    "Mae", "Mateo", "Maya", "Mina", "Nadia", "Nico", "Noah", "Omar",
    "Priya", "Rafael", "Ravi", "Rosa", "Sana", "Sofia", "Tariq", "Theo",
    "Uma", "Valentina", "Vikram", "Yara", "Yusuf", "Zara", "Zoe",
]
LAST_NAMES = [
    "Achebe", "Alvarez", "Andersen", "Bakker", "Bianchi", "Chen", "Costa",
    "Diallo", "Dubois", "Eriksen", "Fischer", "Garcia", "Gupta", "Haddad",
    "Hansen", "Ibrahim", "Ito", "Jensen", "Kaur", "Khan", "Kim", "Kovac",
    "Kumar", "Larsen", "Lee", "Lopez", "Mensah", "Meyer", "Moreau", "Nakamura",
    "Nguyen", "Novak", "Okafor", "Olsen", "Park", "Patel", "Pereira", "Rossi",
    "Sato", "Schmidt", "Silva", "Singh", "Suzuki", "Tanaka", "Tran", "Varga",
    "Wang", "Weber", "Yamamoto", "Zhang", "Zhou",
]
FIRM_PREFIXES = [
    "North", "Summit", "Blue", "Red", "Kite", "Lumen", "Atlas", "Harbor",
    "Cedar", "Vantage", "Orbit", "Pioneer", "Juniper", "Copper", "Bright",
    "Evergreen", "Nimbus", "Sable", "Terra", "Willow",
]
FIRM_SUFFIXES = [
    "Labs", "Works", "Group", "Partners", "Systems", "Collective", "Industries",
    "Ventures", "Studio", "Dynamics",
]


class Simulation:
    def __init__(self, config: Config):
        self.cfg = config.resolved()
        self.rng = random.Random(self.cfg.seed)
        self.agents: dict[int, Agent] = {}
        self.firms: dict[int, Firm] = {}
        self.step_index = 0
        self.history: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []
        self.price = self.cfg.base_price
        self.total_output = 0.0
        self._market_index = 1.0
        self.next_firm_id = 1
        self.used_names: set[str] = set()
        self._total_entries = 0
        self._total_exits = 0
        self._last_step_events: list[dict[str, Any]] = []

        self._create_population()
        self._create_initial_firms()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------
    def _create_population(self) -> None:
        behaviors = list(BEHAVIOR_PROFILES)
        weights = [BEHAVIOR_PROFILES[b]["weight"] for b in behaviors]
        for agent_id in range(1, self.cfg.population + 1):
            behavior = self.rng.choices(behaviors, weights=weights, k=1)[0]
            profile = BEHAVIOR_PROFILES[behavior]
            skill = self._clip(self.rng.gauss(0.56 + profile["skill"], 0.17), 0.14, 1.0)
            ambition = self._clip(
                self.rng.betavariate(2.0, 2.1) + profile["ambition"], 0.02, 0.99
            )
            support = self._clip(
                self.rng.betavariate(2.0, 2.2) + profile["support"], 0.01, 0.99
            )
            mobility = self._clip(
                self.rng.betavariate(2.0, 2.2) + profile["mobility"], 0.02, 0.98
            )
            politics = self._clip(
                self.rng.betavariate(2.0, 2.5) + profile["politics"], 0.01, 0.99
            )
            name = self._unique_name()
            self.agents[agent_id] = Agent(
                id=agent_id,
                name=name,
                behavior=behavior,
                skill=skill,
                ambition=ambition,
                hierarchy_support=support,
                mobility=mobility,
                politics=politics,
            )

    def _unique_name(self) -> str:
        for _ in range(500):
            name = f"{self.rng.choice(FIRST_NAMES)} {self.rng.choice(LAST_NAMES)}"
            if name not in self.used_names:
                self.used_names.add(name)
                return name
        name = f"Agent {len(self.used_names) + 1}"
        self.used_names.add(name)
        return name

    def _unique_firm_name(self) -> str:
        for _ in range(500):
            name = f"{self.rng.choice(FIRM_PREFIXES)} {self.rng.choice(FIRM_SUFFIXES)}"
            if name not in self.used_names:
                self.used_names.add(name)
                return name
        name = f"Firm {self.next_firm_id}"
        self.used_names.add(name)
        return name

    def _random_strategy(self) -> FirmStrategy:
        return FirmStrategy(
            span=self.rng.choice([3, 4, 4, 5, 5, 5, 6, 7]),
            wage_offer=self._clip(self.rng.gauss(1.0, 0.045), 0.90, 1.10),
            growth_appetite=self._clip(self.rng.gauss(1.0, 0.12), 0.70, 1.30),
            meritocracy=self._clip(self.rng.gauss(0.72, 0.09), 0.32, 0.96),
            quality=self._clip(self.rng.gauss(1.0, 0.04), 0.88, 1.12),
        )

    def _new_firm(
        self,
        founder: Agent,
        strategy: FirmStrategy,
        cash: Optional[float] = None,
        entry_step: int = 0,
    ) -> Firm:
        firm_id = self.next_firm_id
        self.next_firm_id += 1
        firm = Firm(
            id=firm_id,
            name=self._unique_firm_name(),
            strategy=strategy,
            founder_id=founder.id,
            cash=self.cfg.initial_cash * 0.9 if cash is None else cash,
            entry_step=entry_step,
        )
        self.firms[firm_id] = firm
        firm.add_employee(founder.id, None, 0, 0.0)
        founder.firm_id = firm.id
        founder.level = 0
        founder.tenure = 0
        founder.employed_since = entry_step
        wage, discount = self._offer_wage(firm, founder, level=0, is_manager=True)
        founder.wage = wage
        founder.career_discount = discount
        firm.target_headcount = 3
        return firm

    def _create_initial_firms(self) -> None:
        n_firms = min(self.cfg.initial_firms, max(1, self.cfg.population // 8))
        candidates = sorted(
            self.agents.values(),
            key=lambda a: 0.62 * a.ambition + 0.38 * a.skill + self.rng.random() * 0.1,
            reverse=True,
        )
        used: set[int] = set()
        for i in range(n_firms):
            founder = next((a for a in candidates if a.id not in used), None)
            if founder is None:
                break
            used.add(founder.id)
            firm = self._new_firm(founder, self._random_strategy(), entry_step=0)
            # Seed each firm with a small founding team.
            initial_reports = self.rng.randint(2, 4)
            for _ in range(initial_reports):
                hire = self._pick_unemployed(exclude=used)
                if hire is None:
                    break
                used.add(hire.id)
                manager_id = firm.ceo_id
                level = firm.level.get(manager_id, 0) + 1
                wage, discount = self._offer_wage(
                    firm, hire, level=level, open_slots=2
                )
                firm.add_employee(hire.id, manager_id, level, wage)
                hire.firm_id = firm.id
                hire.wage = wage
                hire.career_discount = discount
                hire.level = level
                hire.employed_since = 0
            firm.target_headcount = max(3, firm.headcount + self.rng.randint(1, 3))
            firm.age = 0

    def _pick_unemployed(self, exclude: Optional[set[int]] = None) -> Optional[Agent]:
        exclude = exclude or set()
        pool = [
            a
            for a in self.agents.values()
            if a.firm_id is None and a.id not in exclude
        ]
        if not pool:
            return None
        return self.rng.choice(pool)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _clip(value: float, low: float, high: float) -> float:
        return min(high, max(low, value))

    @property
    def alive_firms(self) -> list[Firm]:
        return [f for f in self.firms.values() if f.alive and f.headcount > 0]

    def employed_agents(self) -> list[Agent]:
        return [a for a in self.agents.values() if a.firm_id is not None]

    def _market_wage_index(self) -> float:
        # Cached once per step: this is called for every vacancy/worker offer.
        return self._market_index

    def _refresh_market_index(self) -> None:
        employed = sum(1 for a in self.agents.values() if a.firm_id is not None)
        unemployment = max(0.0, (self.cfg.population - employed) / self.cfg.population)
        # Tight labor markets bid wages up; slack markets push them down.
        self._market_index = 0.86 + 0.24 * (1.0 - unemployment)

    def _offer_wage(
        self,
        firm: Firm,
        agent: Agent,
        level: int,
        is_manager: bool = False,
        open_slots: int = 0,
        prospect: Optional[float] = None,
    ) -> tuple[float, float]:
        rank = max(0, firm.height - 1 - level) if firm.height else 0
        level_factor = 1.0 + 0.10 * rank
        base = (
            self.cfg.base_wage
            * self._market_wage_index()
            * (0.65 + 0.70 * agent.skill)
            * level_factor
            * firm.strategy.wage_offer
        )
        if is_manager:
            base *= 1.12
        if prospect is None:
            prospect = firm.promotion_prospect(agent, open_slots)
        discount = min(
            self.cfg.ladder_discount_cap,
            self.cfg.ladder_wage_discount
            * self.cfg.career_ladder_weight
            * agent.ambition
            * prospect,
        )
        return max(1.0, base * (1.0 - discount)), discount

    def _job_utility(
        self,
        firm: Firm,
        agent: Agent,
        wage: float,
        open_slots: int,
        prospect: Optional[float] = None,
    ) -> float:
        if prospect is None:
            prospect = firm.promotion_prospect(agent, open_slots)
        utility = math.log(max(1.0, wage))
        utility += (
            self.cfg.career_ladder_weight
            * agent.ambition
            * prospect
            * 0.92
        )
        utility += (
            self.cfg.hierarchy_support_bonus
            * agent.hierarchy_support
            * min(1.6, firm.height / 4.0)
        )
        utility += 0.018 * math.log1p(firm.age)
        utility += 0.012 * (1.0 - agent.mobility)
        return utility

    def _current_utility(self, agent: Agent) -> float:
        if agent.firm_id is None:
            return math.log(max(1.0, self.cfg.unemployment_benefit))
        firm = self.firms[agent.firm_id]
        open_slots = max(0, firm.target_headcount - firm.headcount)
        return self._job_utility(firm, agent, agent.wage, open_slots)

    def _promotion_candidate(self, firm: Firm, manager_id: int) -> Optional[int]:
        ics = [
            a
            for a in firm.children.get(manager_id, [])
            if not firm.children.get(a)
        ]
        if len(ics) < 2:
            return None
        return max(
            ics,
            key=lambda aid: self.agents[aid].promotion_score(
                firm.strategy.meritocracy, self.rng
            ),
        )

    def _do_promotion(
        self, firm: Firm, agent_id: int, manager_id: int, reason: str
    ) -> bool:
        agent = self.agents[agent_id]
        if not firm.promote(agent_id, manager_id, self.rng):
            return False
        new_wage, discount = self._offer_wage(
            firm,
            agent,
            level=agent.level,
            is_manager=True,
            open_slots=max(0, firm.target_headcount - firm.headcount),
        )
        agent.wage = max(agent.wage * 1.10, new_wage)
        agent.career_discount = discount
        agent.promotions += 1
        agent.tenure = 0
        firm.promotions += 1
        if reason == "retention":
            firm.retention_promotions += 1
        self._last_step_events.append(
            {
                "step": self.step_index,
                "type": "promotion",
                "firm": firm.name,
                "agent": agent.name,
                "reason": reason,
                "new_height": firm.height,
            }
        )
        return True

    def _promote_capacity(self, firm: Firm) -> bool:
        manager_id = firm.full_manager()
        if manager_id is None:
            # Planned hires can exhaust capacity before the tree itself is full.
            # Pick the widest team with a splittable pair.
            options = [
                m
                for m in firm.managers
                if len(
                    [
                        a
                        for a in firm.children.get(m, [])
                        if not firm.children.get(a)
                    ]
                )
                >= 2
            ]
            if not options:
                return False
            manager_id = max(options, key=lambda m: len(firm.children[m]))
        candidate = self._promotion_candidate(firm, manager_id)
        if candidate is None:
            return False
        return self._do_promotion(firm, candidate, manager_id, "capacity")

    def _ensure_capacity(self, firm: Firm) -> bool:
        if firm.capacity_manager(firm.strategy.span) is not None:
            return True
        for _ in range(2):
            if not self._promote_capacity(firm):
                return False
            if firm.capacity_manager(firm.strategy.span) is not None:
                return True
        return firm.capacity_manager(firm.strategy.span) is not None

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    def run(self) -> dict[str, Any]:
        for _ in range(self.cfg.steps):
            self.step()
        return self.to_dict()

    def step(self) -> dict[str, Any]:
        self._last_step_events = []
        self._refresh_market_index()
        for firm in self.firms.values():
            firm.hires = firm.quits = firm.layoffs = 0
            firm.promotions = firm.retention_promotions = 0
        entries_before = self._total_entries
        exits_before = self._total_exits

        self._production_and_market()
        self._set_targets()
        self._layoffs_and_exits()
        self._retention_promotions()

        vacancies = self._build_vacancies()
        hires, quits = self._match_workers(vacancies)
        self._maybe_entry()

        record = self._record(
            entries=self._total_entries - entries_before,
            exits=self._total_exits - exits_before,
            hires=hires,
            quits=quits,
        )
        self.events.extend(self._last_step_events)
        if len(self.events) > 2000:
            self.events = self.events[-1500:]
        self.step_index += 1
        return record

    # ------------------------------------------------------------------
    # Production, target setting, exit
    # ------------------------------------------------------------------
    def _production_and_market(self) -> None:
        alive = self.alive_firms
        for firm in alive:
            firm._skill_cache = {
                aid: self.agents[aid].skill for aid in firm.employees
            }
            firm._wage_cache = {aid: self.agents[aid].wage for aid in firm.employees}
            firm.compute_economics(1.0, self.cfg.fixed_cost)
        total_output = sum(firm.output for firm in alive)
        self.total_output = total_output
        price = self.cfg.base_price * (
            self.cfg.price_reference / max(1.0, total_output)
        ) ** self.cfg.competition
        self.price = self._clip(price, 0.35, 2.25)
        for firm in alive:
            firm.compute_economics(self.price, self.cfg.fixed_cost)
            firm.cash += firm.profit
            firm.age += 1

    def _set_targets(self) -> None:
        for firm in self.alive_firms:
            headcount = firm.headcount
            margin = firm.profit / max(1.0, firm.revenue)
            if headcount <= 1:
                target = 3
            elif firm.cash < 0.75 * max(1.0, firm.payroll):
                target = max(1, headcount - 2)
            elif margin > 0:
                growth = (
                    0.038
                    * firm.strategy.growth_appetite
                    * (0.55 + min(2.2, margin * 3.8))
                )
                if firm.cash > 3.0 * max(1.0, firm.payroll):
                    growth += 0.012
                target = headcount * (1.0 + growth) + 0.35
            else:
                shrink = min(0.12, 0.030 * min(2.2, -margin * 5.0))
                target = headcount * (1.0 - shrink)
            if firm.age < 8:
                target = max(target, headcount + 1)
            # New firms can buy growth with their initial capital even while
            # they are still below efficient scale.
            if firm.cash > 1.5 * max(1.0, firm.payroll) and headcount < 6:
                target = max(target, headcount + 1)
            firm.target_headcount = int(self._clip(round(target), 1, 95))

    def _layoffs_and_exits(self) -> None:
        for firm in list(self.alive_firms):
            if firm.headcount == 0:
                self._dissolve_firm(firm, "empty")
                continue
            if firm.cash < self.cfg.failure_cash:
                self._dissolve_firm(firm, "insolvent")
                continue
            excess = firm.headcount - firm.target_headcount
            if excess > 0 and (
                firm.cash < 0.8 * max(1.0, firm.payroll) or excess >= 2
            ):
                n = min(
                    self.cfg.max_layoffs_per_step,
                    excess,
                )
                for _ in range(n):
                    if firm.headcount <= 1:
                        break
                    self._layoff_one(firm)
            if not firm.alive:
                self._dissolve_firm(firm, "no-successor")

    def _layoff_one(self, firm: Firm) -> None:
        ics = firm.ic_employees
        if ics:
            victim = min(
                ics,
                key=lambda aid: (
                    0.68 * self.agents[aid].skill
                    + 0.17 * self.agents[aid].hierarchy_support
                    + 0.15 * self.agents[aid].ambition
                    + self.rng.random() * 0.05
                ),
            )
        else:
            managers = firm.managers
            if not managers:
                return
            victim = min(
                managers,
                key=lambda aid: (
                    len(firm.children.get(aid, [])),
                    self.agents[aid].skill,
                ),
            )
        agent = self.agents[victim]
        firm.remove_employee(victim, self.rng)
        firm.layoffs += 1
        agent.firm_id = None
        agent.wage = 0.0
        agent.career_discount = 0.0
        agent.level = 0
        agent.tenure = 0
        agent.employed_since = 0
        self._last_step_events.append(
            {
                "step": self.step_index,
                "type": "layoff",
                "firm": firm.name,
                "agent": agent.name,
            }
        )

    def _dissolve_firm(self, firm: Firm, reason: str) -> None:
        if not firm.alive:
            # It may already have been marked dead by remove_employee.
            pass
        firm.alive = False
        for aid in list(firm.employees):
            agent = self.agents[aid]
            agent.firm_id = None
            agent.wage = 0.0
            agent.career_discount = 0.0
            agent.level = 0
            agent.tenure = 0
            agent.employed_since = 0
        firm.employees.clear()
        firm.manager.clear()
        firm.children.clear()
        firm.level.clear()
        self._total_exits += 1
        self._last_step_events.append(
            {
                "step": self.step_index,
                "type": "exit",
                "firm": firm.name,
                "reason": reason,
            }
        )

    # ------------------------------------------------------------------
    # Promotions
    # ------------------------------------------------------------------
    def _retention_promotions(self) -> None:
        if not self.cfg.retention_promotions or self.cfg.career_ladder_weight <= 0:
            return
        for firm in self.alive_firms:
            if firm.headcount < 4 or firm.manager_ratio >= self.cfg.max_manager_ratio:
                continue
            if firm.cash < 1.1 * max(1.0, firm.payroll):
                continue
            ambitions = [self.agents[a].ambition for a in firm.employees]
            avg_ambition = sum(ambitions) / max(1, len(ambitions))
            pressure = (
                self.cfg.retention_promotion_rate
                * self.cfg.career_ladder_weight
                * (0.45 + avg_ambition)
                * (1.0 + max(0.0, (6 - firm.strategy.span) / 10.0))
            )
            if self.rng.random() >= pressure:
                continue
            options: list[tuple[float, int, int]] = []
            for manager_id in firm.managers:
                ics = [
                    a
                    for a in firm.children.get(manager_id, [])
                    if not firm.children.get(a)
                ]
                if len(ics) < 2:
                    continue
                for aid in ics:
                    agent = self.agents[aid]
                    score = (
                        0.50 * agent.ambition
                        + 0.28 * agent.skill
                        + 0.17 * agent.hierarchy_support
                        + self.rng.random() * 0.10
                    )
                    options.append((score, manager_id, aid))
            if not options:
                continue
            _, manager_id, agent_id = max(options, key=lambda row: row[0])
            self._do_promotion(firm, agent_id, manager_id, "retention")

    # ------------------------------------------------------------------
    # Hiring and worker mobility
    # ------------------------------------------------------------------
    def _build_vacancies(self) -> list[dict[str, Any]]:
        vacancies: list[dict[str, Any]] = []
        slot_id = 0
        for firm in self.alive_firms:
            planned = min(
                self.cfg.max_hires_per_step,
                max(0, firm.target_headcount - firm.headcount),
            )
            if planned <= 0 or firm.cash <= 0:
                continue
            if firm.cash < 0.9 * max(1.0, firm.payroll):
                continue
            if firm.headcount < 3:
                planned = max(planned, 1)
            firm_vacancies = self._vacancies_for_firm(firm, planned)
            for vacancy in firm_vacancies:
                slot_id += 1
                vacancy["slot_id"] = slot_id
            vacancies.extend(firm_vacancies)
        return vacancies

    def _vacancies_for_firm(self, firm: Firm, n: int) -> list[dict[str, Any]]:
        """Build up to ``n`` slots, promoting once if the current tree is full."""
        for _attempt in range(3):
            loads = {
                manager_id: len(firm.children.get(manager_id, []))
                for manager_id in firm.managers
            }
            built: list[dict[str, Any]] = []
            restarted = False
            for _ in range(n):
                candidates = [
                    manager_id
                    for manager_id in firm.managers
                    if loads.get(manager_id, 0) < firm.strategy.span
                ]
                if not candidates:
                    if self._promote_capacity(firm):
                        restarted = True
                        break
                    return built
                manager_id = max(
                    candidates,
                    key=lambda m: (
                        firm.level.get(m, 0),
                        -loads.get(m, 0),
                    ),
                )
                loads[manager_id] = loads.get(manager_id, 0) + 1
                built.append(
                    {
                        "firm_id": firm.id,
                        "manager_id": manager_id,
                        "level": firm.level.get(manager_id, 0) + 1,
                    }
                )
            if not restarted:
                return built
        return []

    def _ranked_vacancies_for_agent(
        self, agent: Agent, vacancies: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        current_utility = self._current_utility(agent)
        move_cost = self.cfg.moving_cost * (0.55 + 0.45 * agent.mobility)
        scored: list[dict[str, Any]] = []
        firm_terms: dict[tuple[int, int], tuple[float, float, float]] = {}
        for vacancy in vacancies:
            firm = self.firms[vacancy["firm_id"]]
            if not firm.alive or agent.firm_id == firm.id:
                continue
            term_key = (firm.id, vacancy["level"])
            if term_key not in firm_terms:
                open_slots = max(0, firm.target_headcount - firm.headcount)
                prospect = firm.promotion_prospect(agent, open_slots)
                wage, discount = self._offer_wage(
                    firm,
                    agent,
                    level=vacancy["level"],
                    open_slots=open_slots,
                    prospect=prospect,
                )
                utility = self._job_utility(
                    firm,
                    agent,
                    wage,
                    open_slots=open_slots,
                    prospect=prospect,
                )
                firm_terms[term_key] = (wage, discount, utility)
            wage, discount, utility = firm_terms[term_key]
            if agent.firm_id is not None:
                utility -= move_cost
            gain = utility - current_utility
            threshold = 0.005 if agent.firm_id is None else 0.018
            if gain <= threshold:
                continue
            scored.append(
                {
                    **vacancy,
                    "agent_id": agent.id,
                    "wage": wage,
                    "discount": discount,
                    "gain": gain,
                    "score": (
                        0.72 * agent.skill
                        + 0.14 * agent.hierarchy_support
                        + 0.08 * agent.ambition
                        + self.rng.random() * 0.06
                    ),
                }
            )
        scored.sort(key=lambda row: row["gain"], reverse=True)
        # Applying to every vacancy would make high-growth markets needlessly
        # expensive.  Four ranked applications are enough to fill the market
        # without every worker chasing the single most attractive firm.
        return scored[:4]

    def _match_workers(
        self, vacancies: list[dict[str, Any]]
    ) -> tuple[int, int]:
        if not vacancies:
            return 0, 0

        unemployed = [a for a in self.agents.values() if a.firm_id is None]
        searchers = [
            a
            for a in self.agents.values()
            if a.firm_id is not None and self.rng.random() < self.cfg.search_fraction
        ]

        proposals: list[tuple[float, int, list[dict[str, Any]]]] = []
        for agent in unemployed + searchers:
            ranked = self._ranked_vacancies_for_agent(agent, vacancies)
            if ranked:
                proposals.append((ranked[0]["gain"], agent.id, ranked))
        # Serial assignment by willingness-to-move avoids the congestion failure
        # where every unemployed worker applies only to the biggest firm.
        proposals.sort(key=lambda row: row[0], reverse=True)

        hires = 0
        quits = 0
        filled_slots: set[int] = set()
        hired_agents: set[int] = set()
        for _, agent_id, ranked in proposals:
            if agent_id in hired_agents:
                continue
            agent = self.agents[agent_id]
            for chosen in ranked:
                if chosen["slot_id"] in filled_slots:
                    continue
                firm = self.firms[chosen["firm_id"]]
                if not firm.alive:
                    continue
                # Re-check capacity: an earlier hire in this same step may have
                # used the slot.  Allocate a fresh slot under the same manager.
                if len(firm.children.get(chosen["manager_id"], [])) >= firm.strategy.span:
                    if not self._ensure_capacity(firm):
                        continue
                    manager_id = firm.capacity_manager(firm.strategy.span)
                    if manager_id is None:
                        continue
                    chosen["manager_id"] = manager_id
                    chosen["level"] = firm.level.get(manager_id, 0) + 1
                old_firm = self.firms.get(agent.firm_id) if agent.firm_id else None
                old_was_alive = old_firm is not None and old_firm.alive
                if old_firm is not None and old_was_alive and old_firm.id != firm.id:
                    old_firm.remove_employee(agent.id, self.rng)
                    old_firm.quits += 1
                    quits += 1
                    if not old_firm.alive:
                        self._dissolve_firm(old_firm, "leader-left")
                level = firm.level.get(chosen["manager_id"], 0) + 1
                wage, discount = self._offer_wage(
                    firm,
                    agent,
                    level=level,
                    open_slots=max(0, firm.target_headcount - firm.headcount),
                )
                firm.add_employee(agent.id, chosen["manager_id"], level, wage)
                agent.firm_id = firm.id
                agent.wage = wage
                agent.career_discount = discount
                agent.level = level
                agent.tenure = 0
                agent.employed_since = self.step_index
                agent.job_changes += 1 if old_was_alive else 0
                firm.hires += 1
                hired_agents.add(agent.id)
                filled_slots.add(chosen["slot_id"])
                hires += 1
                self._last_step_events.append(
                    {
                        "step": self.step_index,
                        "type": "hire",
                        "firm": firm.name,
                        "agent": agent.name,
                        "from": old_firm.name if old_was_alive and old_firm else "pool",
                    }
                )
                break
        return hires, quits

    # ------------------------------------------------------------------
    # Firm entry
    # ------------------------------------------------------------------
    def _maybe_entry(self) -> None:
        if len(self.alive_firms) >= self.cfg.max_firms:
            return
        if self.rng.random() >= self.cfg.entry_rate:
            return
        unemployed = [a for a in self.agents.values() if a.firm_id is None]
        if len(unemployed) < 2:
            return

        # Ambitious, skilled founders are the most likely to start a firm.
        unemployed.sort(
            key=lambda a: 0.58 * a.ambition + 0.42 * a.skill + self.rng.random() * 0.08,
            reverse=True,
        )
        founder = self.rng.choice(unemployed[: max(1, min(6, len(unemployed)))])
        parents = self.alive_firms
        if parents:
            weights = [
                max(0.2, (firm.headcount ** 0.55) * (1.0 + max(0.0, firm.profit) / 500.0))
                for firm in parents
            ]
            parent = self.rng.choices(parents, weights=weights, k=1)[0]
            strategy = parent.strategy.mutated(self.rng, self.cfg.strategy_mutation)
        else:
            strategy = self._random_strategy()
        cash = self.cfg.initial_cash * self.rng.uniform(0.82, 1.12)
        firm = self._new_firm(founder, strategy, cash=cash, entry_step=self.step_index)
        self._total_entries += 1
        firm.hires = 0
        # Founding team: one or two additional people from the pool.
        for _ in range(self.rng.randint(1, 2)):
            if firm.headcount >= firm.strategy.span:
                break
            hire = self._pick_unemployed()
            if hire is None:
                break
            level = firm.level.get(firm.ceo_id, 0) + 1
            wage, discount = self._offer_wage(
                firm, hire, level=level, open_slots=2
            )
            firm.add_employee(hire.id, firm.ceo_id, level, wage)
            hire.firm_id = firm.id
            hire.wage = wage
            hire.career_discount = discount
            hire.level = level
            hire.employed_since = self.step_index
            firm.hires += 1
        firm.target_headcount = firm.headcount + 2
        self._last_step_events.append(
            {
                "step": self.step_index,
                "type": "entry",
                "firm": firm.name,
                "founder": founder.name,
                "strategy_span": strategy.span,
                "parent": parent.name if parents else None,
            }
        )

    # ------------------------------------------------------------------
    # History and export
    # ------------------------------------------------------------------
    def _record(
        self, entries: int, exits: int, hires: int, quits: int
    ) -> dict[str, Any]:
        alive = self.alive_firms
        employed = self.employed_agents()
        n_employed = len(employed)
        total_output = sum(firm.output for firm in alive)
        total_revenue = sum(firm.revenue for firm in alive)
        total_payroll = sum(firm.payroll for firm in alive)
        total_profit = sum(firm.profit for firm in alive)
        manager_counts = sum(len(firm.managers) for firm in alive)
        weighted_height = (
            sum(firm.height * firm.headcount for firm in alive) / n_employed
            if n_employed
            else 0.0
        )
        weighted_manager_ratio = (
            sum(firm.manager_ratio * firm.headcount for firm in alive) / n_employed
            if n_employed
            else 0.0
        )
        tall_firms = [firm for firm in alive if firm.height >= 4]
        flat_firms = [firm for firm in alive if firm.height < 4]
        tall_headcount = sum(firm.headcount for firm in tall_firms)
        flat_headcount = sum(firm.headcount for firm in flat_firms)
        tall_output = sum(firm.output for firm in tall_firms)
        flat_output = sum(firm.output for firm in flat_firms)
        tall_payroll = sum(firm.payroll for firm in tall_firms)
        flat_payroll = sum(firm.payroll for firm in flat_firms)
        tall_employment = tall_headcount
        discounts = [a.career_discount for a in employed]
        supports = [a.hierarchy_support for a in employed]
        prospects = [
            self.firms[a.firm_id].promotion_prospect(
                a, max(0, self.firms[a.firm_id].target_headcount - self.firms[a.firm_id].headcount)
            )
            for a in employed
            if a.firm_id is not None
        ]
        record = {
            "step": self.step_index,
            "firms": len(alive),
            "employed": n_employed,
            "unemployed": self.cfg.population - n_employed,
            "unemployment_rate": round(
                (self.cfg.population - n_employed) / self.cfg.population, 4
            ),
            "avg_firm_size": round(n_employed / max(1, len(alive)), 2),
            "max_firm_size": max((firm.headcount for firm in alive), default=0),
            "avg_height": round(
                sum(firm.height for firm in alive) / max(1, len(alive)), 3
            ),
            "weighted_height": round(weighted_height, 3),
            "avg_manager_ratio": round(
                sum(firm.manager_ratio for firm in alive) / max(1, len(alive)), 4
            ),
            "weighted_manager_ratio": round(weighted_manager_ratio, 4),
            "average_span": round(
                sum(firm.average_span for firm in alive) / max(1, len(alive)), 3
            ),
            "weighted_span_target": round(
                sum(firm.strategy.span * firm.headcount for firm in alive)
                / max(1, n_employed),
                3,
            ),
            "output": round(total_output, 1),
            "output_per_worker": round(total_output / max(1, n_employed), 3),
            "revenue_per_worker": round(total_revenue / max(1, n_employed), 3),
            "wage_per_worker": round(total_payroll / max(1, n_employed), 3),
            "profit_margin": round(total_profit / max(1.0, total_revenue), 4),
            "price": round(self.price, 4),
            "tall_employment_share": round(tall_employment / max(1, n_employed), 4),
            "tall_output_per_worker": round(tall_output / max(1, tall_headcount), 3),
            "flat_output_per_worker": round(flat_output / max(1, flat_headcount), 3),
            "tall_wage_per_worker": round(tall_payroll / max(1, tall_headcount), 3),
            "flat_wage_per_worker": round(flat_payroll / max(1, flat_headcount), 3),
            "tall_manager_ratio": round(
                sum(firm.manager_ratio * firm.headcount for firm in tall_firms)
                / max(1, tall_headcount),
                4,
            ),
            "manager_share": round(manager_counts / max(1, n_employed), 4),
            "career_discount": round(sum(discounts) / max(1, len(discounts)), 4),
            "hierarchy_support": round(sum(supports) / max(1, len(supports)), 4),
            "promotion_prospect": round(sum(prospects) / max(1, len(prospects)), 4),
            "promotions": sum(firm.promotions for firm in alive),
            "retention_promotions": sum(
                firm.retention_promotions for firm in alive
            ),
            "promotion_rate": round(
                sum(firm.promotions for firm in alive) / max(1, n_employed), 5
            ),
            "quit_rate": round(quits / max(1, n_employed), 5),
            "hires": hires,
            "voluntary_quits": quits,
            "layoffs": sum(firm.layoffs for firm in alive),
            "entries": entries,
            "exits": exits,
            "avg_firm_age": round(
                sum(firm.age for firm in alive) / max(1, len(alive)), 2
            ),
        }
        self.history.append(record)
        return record

    def summarize(self, window_fraction: float = 0.25) -> dict[str, Any]:
        if not self.history:
            return {}
        start = int(len(self.history) * (1.0 - window_fraction))
        tail = self.history[max(0, start):]
        numeric_keys = [
            key
            for key, value in tail[0].items()
            if key != "step" and isinstance(value, (int, float))
        ]
        summary: dict[str, Any] = {}
        for key in numeric_keys:
            values = [row[key] for row in tail]
            summary[key] = round(statistics.fmean(values), 4)
        summary["steps"] = len(self.history)
        summary["final_firms"] = len(self.alive_firms)
        summary["total_entries"] = self._total_entries
        summary["total_exits"] = self._total_exits
        summary["survival_rate"] = round(
            len(self.alive_firms)
            / max(1, self.cfg.initial_firms + self._total_entries),
            4,
        )
        behavior_counts = Counter(a.behavior.value for a in self.agents.values())
        summary["behaviors"] = dict(behavior_counts)
        return summary

    def to_dict(
        self,
        include_trees: bool = True,
        max_trees: int = 6,
        include_history: bool = True,
    ) -> dict[str, Any]:
        alive = sorted(self.alive_firms, key=lambda f: (-f.headcount, f.id))
        firms = [firm.snapshot() for firm in alive]
        trees = []
        if include_trees:
            for firm in alive[:max_trees]:
                trees.append(firm.tree_snapshot(self.agents))
        employed = self.employed_agents()
        return {
            "meta": {
                "model": "orgsim",
                "version": "0.1.0",
                "scenario": self.cfg.scenario_name,
                "description": self.cfg.scenario_description,
                "seed": self.cfg.seed,
                "steps": self.cfg.steps,
                "population": self.cfg.population,
                "career_ladder_weight": self.cfg.career_ladder_weight,
                "competition": self.cfg.competition,
            },
            "config": {
                "population": self.cfg.population,
                "initial_firms": self.cfg.initial_firms,
                "steps": self.cfg.steps,
                "seed": self.cfg.seed,
                "competition": self.cfg.competition,
                "career_ladder_weight": self.cfg.career_ladder_weight,
                "base_wage": self.cfg.base_wage,
                "price_reference": round(self.cfg.price_reference, 1),
                "fixed_cost": self.cfg.fixed_cost,
                "retention_promotions": self.cfg.retention_promotions,
            },
            "history": self.history if include_history else self.history[-1:],
            "summary": self.summarize(),
            "firms": firms,
            "trees": trees,
            "events": self.events[-120:],
            "labor_market": {
                "employed": len(employed),
                "unemployed": self.cfg.population - len(employed),
                "behavior_mix": dict(
                    Counter(a.behavior.value for a in employed)
                ),
            },
            "price": round(self.price, 4),
            "final_step": self.history[-1] if self.history else {},
        }
