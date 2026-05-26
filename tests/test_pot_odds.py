"""Tests for pot-odds math and action suggestions."""

from __future__ import annotations

import pytest

from reporter_poker.pot_odds import compute_pot_odds, suggest_action


class TestComputePotOdds:
    def test_basic_2_to_1(self):
        result = compute_pot_odds(pot=100, to_call=50, hero_equity_pct=50)
        assert result.required_equity_pct == pytest.approx(33.333, abs=0.01)
        assert result.ratio_str == "2.0:1"
        assert result.is_plus_ev is True
        assert result.edge_pct == pytest.approx(50 - 33.333, abs=0.01)

    def test_free_call(self):
        result = compute_pot_odds(pot=100, to_call=0, hero_equity_pct=20)
        assert result.required_equity_pct == 0.0
        assert result.ratio_str == "free"
        assert result.is_plus_ev is True
        assert result.edge_pct == 20.0

    def test_minus_ev(self):
        result = compute_pot_odds(pot=10, to_call=50, hero_equity_pct=20)
        # required = 50 / 60 = 83.3%
        assert result.required_equity_pct == pytest.approx(83.333, abs=0.01)
        assert result.is_plus_ev is False
        assert result.edge_pct < 0

    def test_break_even_is_not_plus_ev(self):
        # Strictly greater than required for +EV.
        result = compute_pot_odds(pot=100, to_call=50, hero_equity_pct=33.333)
        assert result.is_plus_ev is False

    def test_negative_inputs_rejected(self):
        with pytest.raises(ValueError):
            compute_pot_odds(pot=-1, to_call=10, hero_equity_pct=50)
        with pytest.raises(ValueError):
            compute_pot_odds(pot=10, to_call=-1, hero_equity_pct=50)


class TestSuggestAction:
    def test_check_when_no_call_and_low_equity(self):
        assert suggest_action(equity_pct=30, required_pct=0, to_call=0) == "check"

    def test_bet_when_no_call_and_strong_equity(self):
        assert suggest_action(equity_pct=70, required_pct=0, to_call=0) == "bet"

    def test_raise_when_big_edge(self):
        # equity 60 vs required 30 -> edge 30 > 5 -> raise
        assert suggest_action(equity_pct=60, required_pct=30, to_call=10) == "raise"

    def test_call_when_small_edge(self):
        # equity 33 vs required 30 -> edge 3 (< 5 raise margin) -> call
        assert suggest_action(equity_pct=33, required_pct=30, to_call=10) == "call"

    def test_fold_when_negative_edge(self):
        assert suggest_action(equity_pct=20, required_pct=40, to_call=10) == "fold"
