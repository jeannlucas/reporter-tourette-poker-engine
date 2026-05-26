"""Smoke tests for the FastAPI web layer."""

from __future__ import annotations

from fastapi.testclient import TestClient

from reporter_poker.web.server import app

client = TestClient(app)


def test_aa_preflop_high_winrate():
    """AA heads-up should produce a high hero equity through the endpoint."""
    response = client.post(
        "/api/analyze",
        json={
            "hole_cards": "As Ad",
            "board": "",
            "num_opponents": 1,
            "pot": 100,
            "to_call": 50,
            "iterations": 5000,
        },
    )
    assert response.status_code == 200
    body = response.json()

    assert body["street"] == "preflop"
    assert body["hand"]["is_preflop"] is True
    assert body["hand"]["category"] == "PAIR"
    # AA preflop is ~85% — with 5k sims, generous lower bound.
    assert body["equity"]["win_pct"] > 75
    assert body["equity"]["iterations"] == 5000
    assert body["suggestion"] in {"fold", "call", "raise", "check", "bet"}


def test_flop_returns_outs_and_potodds():
    response = client.post(
        "/api/analyze",
        json={
            "hole_cards": "As Ad",
            "board": "Kc 7h 2d",
            "num_opponents": 1,
            "pot": 100,
            "to_call": 50,
            "iterations": 2000,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["street"] == "flop"
    assert body["hand"]["category"] == "PAIR"
    assert body["outs"]["count"] >= 1
    assert body["pot_odds"]["ratio_str"] == "2.0:1"
    assert body["pot_odds"]["required_equity_pct"] > 33
    assert body["pot_odds"]["required_equity_pct"] < 34


def test_invalid_card_returns_400():
    response = client.post(
        "/api/analyze",
        json={
            "hole_cards": "Xs Ad",
            "board": "",
            "num_opponents": 1,
            "pot": 0,
            "to_call": 0,
            "iterations": 1000,
        },
    )
    assert response.status_code == 400
    assert "Invalid" in response.json()["detail"] or "card" in response.json()["detail"].lower()


def test_duplicate_card_returns_400():
    response = client.post(
        "/api/analyze",
        json={
            "hole_cards": "As Ad",
            "board": "As Kd Qc",
            "num_opponents": 1,
            "pot": 0,
            "to_call": 0,
            "iterations": 1000,
        },
    )
    assert response.status_code == 400
    assert "Duplicate" in response.json()["detail"]


def test_bad_board_size_returns_400():
    response = client.post(
        "/api/analyze",
        json={
            "hole_cards": "As Ad",
            "board": "Kc",  # impossible: 1 card
            "num_opponents": 1,
            "pot": 0,
            "to_call": 0,
            "iterations": 1000,
        },
    )
    assert response.status_code == 400


def test_wrong_hole_count_returns_400():
    response = client.post(
        "/api/analyze",
        json={
            "hole_cards": "As",  # only one card
            "board": "",
            "num_opponents": 1,
            "pot": 0,
            "to_call": 0,
            "iterations": 1000,
        },
    )
    assert response.status_code == 400


def test_index_serves_html():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Reporter Tourette" in response.text


def test_static_css_served():
    response = client.get("/static/style.css")
    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]
