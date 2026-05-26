"""Tests for Monte Carlo equity and outs counting."""

from __future__ import annotations

import random

import pytest

from reporter_poker.equity import count_outs, simulate_equity
from reporter_poker.game_state import GameState, parse_cards
from reporter_poker.hand_evaluator import HandCategory


def test_aa_preflop_heads_up():
    """AA vs random hand heads-up should converge to ~85.2% equity."""
    state = GameState(
        hole_cards=tuple(parse_cards("As Ad")),  # type: ignore[arg-type]
        num_opponents=1,
    )
    rng = random.Random(20260526)
    result = simulate_equity(state, iterations=25_000, rng=rng)

    hero_equity = result.win_pct + result.tie_pct / 2.0
    # Textbook AA preflop heads-up: ~85.2%. Allow ±1.5% Monte Carlo tolerance.
    assert 83.7 <= hero_equity <= 86.7, f"unexpected AA equity: {hero_equity:.2f}%"
    assert result.iterations == 25_000


def test_27o_preflop_heads_up_weak():
    """7-2 offsuit is the canonical weakest preflop hand vs random."""
    state = GameState(
        hole_cards=tuple(parse_cards("7c 2d")),  # type: ignore[arg-type]
        num_opponents=1,
    )
    rng = random.Random(20260526)
    result = simulate_equity(state, iterations=10_000, rng=rng)
    hero_equity = result.win_pct + result.tie_pct / 2.0
    # Theory ~34.6% — generous tolerance for 10k sims.
    assert 30.0 <= hero_equity <= 40.0


def test_equity_percentages_sum_to_100():
    state = GameState(
        hole_cards=tuple(parse_cards("As Kd")),  # type: ignore[arg-type]
        board=tuple(parse_cards("Qc Jh Th")),
        num_opponents=2,
    )
    result = simulate_equity(state, iterations=2_000, rng=random.Random(1))
    total = result.win_pct + result.tie_pct + result.loss_pct
    assert abs(total - 100.0) < 1e-6


def test_made_flush_vs_one_opp_high_equity():
    """Flopped nut flush should have very high equity heads-up."""
    state = GameState(
        hole_cards=tuple(parse_cards("As Ks")),  # type: ignore[arg-type]
        board=tuple(parse_cards("Qs Js 5s")),
        num_opponents=1,
    )
    rng = random.Random(7)
    result = simulate_equity(state, iterations=5_000, rng=rng)
    hero_equity = result.win_pct + result.tie_pct / 2.0
    assert hero_equity > 95.0


def test_invalid_iterations():
    state = GameState(hole_cards=tuple(parse_cards("As Kd")))  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        simulate_equity(state, iterations=0)


def test_outs_flush_draw():
    """As Ks on Qs Js 4d — 9 flush outs, plus straight outs from Tx."""
    state = GameState(
        hole_cards=tuple(parse_cards("As Ks")),  # type: ignore[arg-type]
        board=tuple(parse_cards("Qs Js 4d")),
        num_opponents=1,
    )
    result = count_outs(state)
    # Current category is High Card, so any pairing card also counts here:
    # 9 spades (flush) + 3 non-spade Tens (straight) + pair outs for A/K/Q/J/4
    # = 26 unique cards after deduplicating 4s. Wide guard for category logic.
    assert 9 <= len(result.outs) <= 30
    assert result.current_category is HandCategory.HIGH_CARD


def test_outs_preflop_empty():
    state = GameState(hole_cards=tuple(parse_cards("As Kd")))  # type: ignore[arg-type]
    result = count_outs(state)
    assert result.outs == ()
    assert result.next_card_improve_pct == 0.0


def test_outs_river_empty():
    state = GameState(
        hole_cards=tuple(parse_cards("As Kd")),  # type: ignore[arg-type]
        board=tuple(parse_cards("Qs Js Ts 5h 2c")),
    )
    result = count_outs(state)
    assert result.outs == ()
