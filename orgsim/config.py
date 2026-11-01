"""Configuration objects for the organisation-evolution simulation.

The model is deliberately dependency-free.  All tunable assumptions live here so
that a scenario is just a named bundle of parameters, not a different simulator.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any


@dataclass(frozen=True)
class Config:
    """Parameters for one simulation run."""

    # --- population and time -------------------------------------------------
    population: int = 420
    initial_firms: int = 10
    steps: int = 140
    seed: int = 42

    # --- production and market ----------------------------------------------
    output_scale: float = 100.0
    base_price: float = 1.0
    #: How strongly aggregate output pushes the price down. 0 = fixed price,
    #: 1 = strongly contested market.
    competition: float = 0.65
    #: Reference output at which the price is ``base_price``.
    price_reference: float = 0.0  # computed from population if left at 0
    fixed_cost: float = 70.0
    initial_cash: float = 900.0

    # --- labour market ------------------------------------------------------
    base_wage: float = 41.0
    unemployment_benefit: float = 9.0
    search_fraction: float = 0.38
    moving_cost: float = 0.055
    max_hires_per_step: int = 3
    max_layoffs_per_step: int = 2

    # --- hierarchy and promotion --------------------------------------------
    #: Workers value promotion prospects.  Set to zero for the counterfactual.
    career_ladder_weight: float = 1.0
    #: Maximum share of wages workers will give up for a good career ladder.
    ladder_wage_discount: float = 0.85
    ladder_discount_cap: float = 0.30
    #: Extra utility from working in a tall hierarchy, independent of promotion.
    hierarchy_support_bonus: float = 0.07
    #: Firms create retention promotions even when growth does not require them.
    retention_promotions: bool = True
    retention_promotion_rate: float = 0.16
    max_manager_ratio: float = 0.38
    min_retention_team: int = 3

    # --- entry, exit, evolution ---------------------------------------------
    entry_rate: float = 0.065
    max_firms: int = 22
    failure_cash: float = -260.0
    strategy_mutation: float = 0.18

    # --- meta ---------------------------------------------------------------
    scenario_name: str = "baseline"
    scenario_description: str = ""
    notes: dict[str, Any] = field(default_factory=dict)

    def resolved(self) -> "Config":
        """Return a copy with derived defaults filled in."""
        ref = self.price_reference
        if ref <= 0:
            ref = self.population * 0.52 * self.output_scale
        return replace(self, price_reference=ref)


@dataclass
class FirmStrategy:
    """Heritable operating choices of a firm.

    ``span`` is the most important gene: a smaller span of control produces a
    taller hierarchy for a given headcount, more promotion slots, and more
    managerial overhead.  The other genes let firms differ in wage policy,
    growth appetite, meritocracy, and operating quality.
    """

    span: int = 5
    wage_offer: float = 1.0
    growth_appetite: float = 1.0
    meritocracy: float = 0.72
    quality: float = 1.0

    def mutated(self, rng, strength: float) -> "FirmStrategy":
        span = int(round(self.span + rng.choice((-1, 0, 0, 1)) * (rng.random() < 0.7)))
        return FirmStrategy(
            span=min(8, max(2, span)),
            wage_offer=min(1.10, max(0.90, self.wage_offer + rng.gauss(0, strength * 0.08))),
            growth_appetite=min(
                1.30, max(0.70, self.growth_appetite + rng.gauss(0, strength * 0.16))
            ),
            meritocracy=min(
                0.98, max(0.30, self.meritocracy + rng.gauss(0, strength * 0.12))
            ),
            quality=min(1.12, max(0.88, self.quality + rng.gauss(0, strength * 0.07))),
        )


# The baseline bundle is used when a scenario only changes one or two knobs.
def baseline_config(**overrides: Any) -> Config:
    cfg = Config(
        scenario_name="baseline",
        scenario_description=(
            "Competitive output market, career-minded workers, retention promotions. "
            "This is the hypothesis-testing condition."
        ),
    )
    return replace(cfg, **overrides).resolved()
