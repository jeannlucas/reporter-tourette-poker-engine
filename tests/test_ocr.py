"""Tests for the OCR parsing/validation layer (Ollama not required)."""

from __future__ import annotations

import json

import pytest

from reporter_poker.web.ocr import (
    OcrBadResponse,
    parse_ocr_response,
)


class TestParseOcrResponse:
    def test_happy_path(self):
        payload = json.dumps({
            "hole_cards": ["As", "Kd"],
            "board": ["Qh", "Jc", "Th"],
            "pot": 200,
            "to_call": 50,
            "num_opponents": 2,
        })
        result = parse_ocr_response(payload)
        assert result.hole_cards == ["As", "Kd"]
        assert result.board == ["Qh", "Jc", "Th"]
        assert result.pot == 200
        assert result.to_call == 50
        assert result.num_opponents == 2
        assert result.warnings == []

    def test_strips_markdown_fence(self):
        text = '```json\n{"hole_cards": ["As", "Kd"], "board": [], "pot": null, "to_call": null, "num_opponents": null}\n```'
        result = parse_ocr_response(text)
        assert result.hole_cards == ["As", "Kd"]
        assert result.pot is None

    def test_strips_prose_around_json(self):
        text = 'Sure! Here is the data:\n{"hole_cards": ["As", "Kd"], "board": [], "pot": null, "to_call": null, "num_opponents": 3}\nLet me know if you want more.'
        result = parse_ocr_response(text)
        assert result.hole_cards == ["As", "Kd"]
        assert result.num_opponents == 3

    def test_invalid_card_is_flagged_not_fatal(self):
        payload = json.dumps({
            "hole_cards": ["As", "X9"],  # X9 is invalid
            "board": [],
            "pot": None, "to_call": None, "num_opponents": None,
        })
        result = parse_ocr_response(payload)
        assert result.hole_cards == ["As"]
        assert any("X9" in w for w in result.warnings)

    def test_ten_alias_is_normalized(self):
        payload = json.dumps({
            "hole_cards": ["10h", "10c"],
            "board": [], "pot": None, "to_call": None, "num_opponents": None,
        })
        result = parse_ocr_response(payload)
        assert result.hole_cards == ["Th", "Tc"]

    def test_case_is_normalized(self):
        payload = json.dumps({
            "hole_cards": ["aS", "kD"],
            "board": ["qH", "jC", "tH"],
            "pot": None, "to_call": None, "num_opponents": None,
        })
        result = parse_ocr_response(payload)
        assert result.hole_cards == ["As", "Kd"]
        assert result.board == ["Qh", "Jc", "Th"]

    def test_duplicate_card_inside_field_is_dropped(self):
        payload = json.dumps({
            "hole_cards": ["As", "As"],
            "board": [], "pot": None, "to_call": None, "num_opponents": None,
        })
        result = parse_ocr_response(payload)
        assert result.hole_cards == ["As"]
        assert any("duplicada" in w for w in result.warnings)

    def test_cross_duplicate_between_hole_and_board_is_warned(self):
        payload = json.dumps({
            "hole_cards": ["As", "Kd"],
            "board": ["As", "Qh", "Jc"],
            "pot": None, "to_call": None, "num_opponents": None,
        })
        result = parse_ocr_response(payload)
        assert any("repetidas" in w for w in result.warnings)

    def test_three_hole_cards_trimmed(self):
        payload = json.dumps({
            "hole_cards": ["As", "Kd", "Qh"],
            "board": [], "pot": None, "to_call": None, "num_opponents": None,
        })
        result = parse_ocr_response(payload)
        assert len(result.hole_cards) == 2
        assert any("hole_cards com 3" in w for w in result.warnings)

    def test_invalid_board_size_is_warned(self):
        payload = json.dumps({
            "hole_cards": ["As", "Kd"],
            "board": ["Qh", "Jc"],  # 2 cards is not a valid street
            "pot": None, "to_call": None, "num_opponents": None,
        })
        result = parse_ocr_response(payload)
        assert any("flop/turn/river" in w for w in result.warnings)

    def test_num_opponents_out_of_range(self):
        payload = json.dumps({
            "hole_cards": [], "board": [],
            "pot": None, "to_call": None, "num_opponents": 12,
        })
        result = parse_ocr_response(payload)
        assert result.num_opponents is None
        assert any("num_opponents" in w for w in result.warnings)

    def test_negative_pot_is_dropped(self):
        payload = json.dumps({
            "hole_cards": [], "board": [],
            "pot": -10, "to_call": None, "num_opponents": None,
        })
        result = parse_ocr_response(payload)
        assert result.pot is None
        assert any("pot negativo" in w for w in result.warnings)

    def test_non_numeric_pot_string_is_dropped(self):
        payload = json.dumps({
            "hole_cards": [], "board": [],
            "pot": "abc", "to_call": None, "num_opponents": None,
        })
        result = parse_ocr_response(payload)
        assert result.pot is None
        assert any("pot" in w and "não numérico" in w for w in result.warnings)

    def test_empty_response_raises(self):
        with pytest.raises(OcrBadResponse):
            parse_ocr_response("")

    def test_no_json_raises(self):
        with pytest.raises(OcrBadResponse):
            parse_ocr_response("just a sentence, no json here")

    def test_missing_keys_default_to_empty_or_none(self):
        result = parse_ocr_response("{}")
        assert result.hole_cards == []
        assert result.board == []
        assert result.pot is None
        assert result.to_call is None
        assert result.num_opponents is None
        assert result.warnings == []
