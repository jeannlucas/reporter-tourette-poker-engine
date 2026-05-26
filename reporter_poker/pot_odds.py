"""Pot-odds math and a deliberately simple action-suggestion heuristic."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PotOddsResult:
    """Pot-odds breakdown for a call decision.

    Attributes:
        required_equity_pct: minimum hero equity (%) for a call to break even.
        ratio_str: pot:call ratio (e.g. "2.0:1"), or "free" when to_call=0.
        is_plus_ev: True if hero's equity strictly exceeds required.
        edge_pct: hero_equity_pct - required_equity_pct (negative when -EV).
    """

    required_equity_pct: float
    ratio_str: str
    is_plus_ev: bool
    edge_pct: float


def compute_pot_odds(pot: float, to_call: float, hero_equity_pct: float) -> PotOddsResult:
    """Compute required equity and compare it with hero's estimated equity.

    Formula: required_equity = to_call / (pot + to_call).

    If to_call is zero, no equity is required (it is a free card / check) and
    we report "free" as the ratio.
    """
    if pot < 0 or to_call < 0:
        raise ValueError(f"pot and to_call must be non-negative (got {pot}, {to_call})")

    if to_call == 0:
        return PotOddsResult(
            required_equity_pct=0.0,
            ratio_str="free",
            is_plus_ev=True,
            edge_pct=hero_equity_pct,
        )

    required = to_call / (pot + to_call) * 100.0
    ratio = pot / to_call
    return PotOddsResult(
        required_equity_pct=required,
        ratio_str=f"{ratio:.1f}:1",
        is_plus_ev=hero_equity_pct > required,
        edge_pct=hero_equity_pct - required,
    )


# Heuristic thresholds, exposed as constants so they show up in the docs.
RAISE_EDGE_PCT = 5.0  # equity must beat required by this margin to raise
STRONG_EQUITY_PCT = 65.0  # equity threshold for value-betting an unraised pot


def suggest_action(
    equity_pct: float,
    required_pct: float,
    to_call: float,
    raise_edge: float = RAISE_EDGE_PCT,
    strong_equity: float = STRONG_EQUITY_PCT,
) -> str:
    """Suggest fold / call / raise / check / bet from equity and pot odds.

    This is a *pedagogical* MVP heuristic. It compares hero's raw equity
    against pot odds; it deliberately ignores position, stack depth, opponent
    ranges, fold equity, and bet sizing. Treat it as a sanity prompt, not as
    a solver output.
    """
    if to_call == 0:
        return "bet" if equity_pct >= strong_equity else "check"

    if equity_pct - required_pct > raise_edge:
        return "raise"
    if equity_pct >= required_pct:
        return "call"
    return "fold"
