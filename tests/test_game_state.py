"""Tests for GameState validation and card parsing."""

from __future__ import annotations

import pytest
from treys import Card

from reporter_poker.game_state import GameState, parse_card, parse_cards


class TestParseCard:
    def test_basic(self):
        assert parse_card("As") == Card.new("As")
        assert parse_card("Th") == Card.new("Th")
        assert parse_card("2c") == Card.new("2c")

    def test_case_insensitive(self):
        assert parse_card("aS") == Card.new("As")
        assert parse_card("KD") == Card.new("Kd")

    def test_ten_alias(self):
        assert parse_card("10h") == Card.new("Th")
        assert parse_card("10s") == Card.new("Ts")

    def test_whitespace(self):
        assert parse_card("  As  ") == Card.new("As")

    def test_empty(self):
        with pytest.raises(ValueError):
            parse_card("")

    def test_bad_rank(self):
        with pytest.raises(ValueError):
            parse_card("Xs")
        with pytest.raises(ValueError):
            parse_card("1s")

    def test_bad_suit(self):
        with pytest.raises(ValueError):
            parse_card("Ax")

    def test_too_long(self):
        with pytest.raises(ValueError):
            parse_card("Assh")

    def test_non_string(self):
        with pytest.raises(ValueError):
            parse_card(42)  # type: ignore[arg-type]


class TestParseCards:
    def test_space_separated(self):
        cards = parse_cards("As Kd 2c")
        assert len(cards) == 3

    def test_comma_separated(self):
        cards = parse_cards("As,Kd,2c")
        assert len(cards) == 3

    def test_mixed_separators(self):
        cards = parse_cards("As, Kd  2c")
        assert len(cards) == 3

    def test_empty(self):
        assert parse_cards("") == ()
        assert parse_cards("   ") == ()


class TestGameState:
    def _hole(self):
        return (parse_card("As"), parse_card("Kd"))

    def test_preflop_valid(self):
        state = GameState(hole_cards=self._hole(), num_opponents=1)
        assert state.street == "preflop"
        assert state.board == ()

    def test_flop_valid(self):
        board = parse_cards("Qc Jh Th")
        state = GameState(hole_cards=self._hole(), board=board, num_opponents=2)
        assert state.street == "flop"

    def test_turn_valid(self):
        board = parse_cards("Qc Jh Th 2c")
        state = GameState(hole_cards=self._hole(), board=board)
        assert state.street == "turn"

    def test_river_valid(self):
        board = parse_cards("Qc Jh Th 2c 3d")
        state = GameState(hole_cards=self._hole(), board=board)
        assert state.street == "river"

    def test_board_size_1_invalid(self):
        with pytest.raises(ValueError, match="Board size"):
            GameState(hole_cards=self._hole(), board=parse_cards("Qc"))

    def test_board_size_2_invalid(self):
        with pytest.raises(ValueError, match="Board size"):
            GameState(hole_cards=self._hole(), board=parse_cards("Qc Jh"))

    def test_board_size_6_invalid(self):
        with pytest.raises(ValueError, match="Board size"):
            GameState(
                hole_cards=self._hole(),
                board=parse_cards("Qc Jh Th 2c 3d 4s"),
            )

    def test_duplicate_in_board(self):
        with pytest.raises(ValueError, match="Duplicate"):
            GameState(
                hole_cards=self._hole(),
                board=parse_cards("Qc Jh Qc"),
            )

    def test_duplicate_between_hole_and_board(self):
        hole = (parse_card("As"), parse_card("Kd"))
        with pytest.raises(ValueError, match="Duplicate"):
            GameState(hole_cards=hole, board=parse_cards("As Jh Th"))

    def test_zero_opponents_invalid(self):
        with pytest.raises(ValueError, match="num_opponents"):
            GameState(hole_cards=self._hole(), num_opponents=0)

    def test_nine_opponents_invalid(self):
        with pytest.raises(ValueError, match="num_opponents"):
            GameState(hole_cards=self._hole(), num_opponents=9)

    def test_negative_pot(self):
        with pytest.raises(ValueError, match="pot"):
            GameState(hole_cards=self._hole(), pot=-1)

    def test_negative_to_call(self):
        with pytest.raises(ValueError, match="to_call"):
            GameState(hole_cards=self._hole(), to_call=-1)

    def test_known_cards(self):
        board = parse_cards("Qc Jh Th")
        state = GameState(hole_cards=self._hole(), board=board)
        assert len(state.known_cards) == 5
