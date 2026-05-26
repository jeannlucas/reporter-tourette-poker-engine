"""Tests for hand evaluation against known categories."""

from __future__ import annotations

from reporter_poker.game_state import parse_cards
from reporter_poker.hand_evaluator import (
    HandCategory,
    evaluate_hand,
    format_card,
)


def _eval(hole_str: str, board_str: str):
    return evaluate_hand(parse_cards(hole_str), parse_cards(board_str))


def test_royal_flush():
    result = _eval("As Ks", "Qs Js Ts 2c 3d")
    assert result.category is HandCategory.ROYAL_FLUSH
    assert "Royal" in result.label


def test_straight_flush_non_royal():
    result = _eval("9s 8s", "7s 6s 5s 2c 3d")
    assert result.category is HandCategory.STRAIGHT_FLUSH
    assert "Royal" not in result.label


def test_four_of_a_kind():
    result = _eval("As Ad", "Ac Ah Ks 2c 3d")
    assert result.category is HandCategory.FOUR_OF_A_KIND


def test_full_house():
    result = _eval("As Ad", "Ac Ks Kd 2c 3d")
    assert result.category is HandCategory.FULL_HOUSE


def test_flush():
    result = _eval("As Ks", "Qs Js 9s 2c 3d")
    assert result.category is HandCategory.FLUSH


def test_straight():
    result = _eval("9h 8d", "7c 6s 5h 2c 3d")
    assert result.category is HandCategory.STRAIGHT


def test_three_of_a_kind():
    result = _eval("As Ad", "Ac Ks 2c")
    assert result.category is HandCategory.THREE_OF_A_KIND


def test_two_pair():
    result = _eval("As Ks", "Ad Kd 2c")
    assert result.category is HandCategory.TWO_PAIR


def test_pair():
    result = _eval("As Ad", "Kc Jh 2c")
    assert result.category is HandCategory.PAIR


def test_high_card():
    result = _eval("As Kd", "Qc Jh 9s")
    assert result.category is HandCategory.HIGH_CARD


def test_preflop_pocket_pair():
    result = _eval("As Ad", "")
    assert result.is_preflop is True
    assert result.category is HandCategory.PAIR


def test_preflop_high_card():
    result = _eval("As Kd", "")
    assert result.is_preflop is True
    assert result.category is HandCategory.HIGH_CARD
    assert "AKo" in result.label  # unsuited


def test_preflop_suited():
    result = _eval("As Ks", "")
    assert "AKs" in result.label


def test_category_ordering():
    assert HandCategory.FLUSH.beats(HandCategory.STRAIGHT)
    assert HandCategory.ROYAL_FLUSH.beats(HandCategory.STRAIGHT_FLUSH)
    assert not HandCategory.PAIR.beats(HandCategory.PAIR)


def test_format_card_roundtrip():
    cards = parse_cards("As Kd Th 2c")
    formatted = [format_card(c) for c in cards]
    assert formatted == ["As", "Kd", "Th", "2c"]
