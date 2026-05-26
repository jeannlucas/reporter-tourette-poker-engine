"""Equity estimation via Monte Carlo, plus a simple outs counter."""

from __future__ import annotations

import random
from dataclasses import dataclass

from treys import Card, Evaluator

from .game_state import GameState
from .hand_evaluator import HandCategory, evaluate_hand

_evaluator = Evaluator()

# Pre-built deck of all 52 treys card ints. Built once at import time.
ALL_52: tuple[int, ...] = tuple(
    Card.new(r + s) for r in "23456789TJQKA" for s in "shdc"
)


@dataclass(frozen=True)
class EquityResult:
    """Outcome distribution of a Monte Carlo run.

    Percentages sum to ~100 (rounding aside). `tie_pct` counts pots split
    with at least one opponent; it is not split into 2-way / 3-way ties.
    """

    win_pct: float
    tie_pct: float
    loss_pct: float
    iterations: int


@dataclass(frozen=True)
class OutsResult:
    """Outs analysis for the current street.

    `outs` are the unseen cards that, if dealt next, lift hero's hand
    category above its current category. `next_card_improve_pct` is the
    naive probability that the very next card improves the category
    (outs / unseen). This is the textbook "study" definition of outs,
    not equity-against-range.
    """

    outs: tuple[int, ...]
    next_card_improve_pct: float
    current_category: HandCategory


def simulate_equity(
    state: GameState,
    iterations: int = 25_000,
    rng: random.Random | None = None,
) -> EquityResult:
    """Estimate hero's equity by sampling opponent holes + remaining board.

    Each iteration:
        - Samples `2*num_opponents + (5 - len(board))` distinct cards from
          the unseen deck.
        - Deals two to each opponent, completes the board.
        - Evaluates every player's 7-card best, picks the min score (winner).
        - Tallies hero win / tie / loss.

    Args:
        state: the decision-point snapshot.
        iterations: number of Monte Carlo trials.
        rng: optional injected RNG for deterministic tests.

    Returns:
        EquityResult with win/tie/loss percentages.
    """
    if iterations <= 0:
        raise ValueError(f"iterations must be positive, got {iterations}")

    rng = rng or random.Random()

    known = set(state.known_cards)
    unknown = [c for c in ALL_52 if c not in known]

    hero_hole = list(state.hole_cards)
    base_board = list(state.board)
    board_to_deal = 5 - len(base_board)
    cards_per_iter = 2 * state.num_opponents + board_to_deal

    if cards_per_iter > len(unknown):
        raise ValueError(
            f"Not enough unseen cards for {state.num_opponents} opponents "
            f"on this street: need {cards_per_iter}, have {len(unknown)}"
        )

    wins = ties = losses = 0
    n_opps = state.num_opponents

    for _ in range(iterations):
        sample = rng.sample(unknown, cards_per_iter)
        # Opponent holes occupy slots [0 .. 2*n_opps), then board fillers.
        full_board = base_board + sample[2 * n_opps:]

        hero_score = _evaluator.evaluate(full_board, hero_hole)

        best_opp = 7463  # worse than any valid treys score (1..7462)
        for i in range(n_opps):
            opp_hole = sample[2 * i : 2 * i + 2]
            opp_score = _evaluator.evaluate(full_board, opp_hole)
            if opp_score < best_opp:
                best_opp = opp_score

        if hero_score < best_opp:
            wins += 1
        elif hero_score == best_opp:
            ties += 1
        else:
            losses += 1

    return EquityResult(
        win_pct=wins / iterations * 100.0,
        tie_pct=ties / iterations * 100.0,
        loss_pct=losses / iterations * 100.0,
        iterations=iterations,
    )


def count_outs(state: GameState) -> OutsResult:
    """Count unseen cards that lift hero's hand category on the next street.

    Defined only for flop (3 cards) and turn (4 cards). At preflop and river
    the concept doesn't apply and we return zero outs.

    Note: "out" here means a card that strictly improves hero's *category*
    (e.g. pair -> two pair). This is the common study definition but does
    not account for opponent ranges or kicker plays.
    """
    if len(state.board) not in (3, 4):
        current = evaluate_hand(state.hole_cards, state.board).category
        return OutsResult(outs=(), next_card_improve_pct=0.0, current_category=current)

    current = evaluate_hand(state.hole_cards, state.board).category

    known = set(state.known_cards)
    unknown = [c for c in ALL_52 if c not in known]

    outs: list[int] = []
    for c in unknown:
        new_board = list(state.board) + [c]
        new_category = evaluate_hand(state.hole_cards, new_board).category
        if new_category.beats(current):
            outs.append(c)

    return OutsResult(
        outs=tuple(outs),
        next_card_improve_pct=len(outs) / len(unknown) * 100.0,
        current_category=current,
    )
