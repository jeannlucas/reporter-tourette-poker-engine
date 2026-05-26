"""Tests for /api/hands endpoints using a temporary SQLite database."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from reporter_poker.history import HandRepository
from reporter_poker.web.server import app, get_repository


@pytest.fixture
def client(tmp_path):
    """TestClient with the repository pointed at a per-test SQLite file."""
    repo = HandRepository(tmp_path / "history.db")
    app.dependency_overrides[get_repository] = lambda: repo
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_repository, None)


def _sample_payload(**overrides) -> dict:
    base = {
        "hole_cards": "As Ad",
        "board": "Kc 7h 2d",
        "num_opponents": 1,
        "pot": 100.0,
        "to_call": 50.0,
        "street": "flop",
        "win_pct": 88.4,
        "tie_pct": 0.2,
        "loss_pct": 11.4,
        "iterations": 25000,
        "hand_category": "PAIR",
        "hand_label": "Pair",
        "is_preflop": False,
        "outs_count": 11,
        "outs_cards": "2s 2h 2c 7s 7d 7c Ks Kh Kd Ah Ac",
        "next_card_improve_pct": 23.4,
        "required_equity_pct": 33.33,
        "ratio_str": "2.0:1",
        "is_plus_ev": True,
        "edge_pct": 55.07,
        "suggestion": "raise",
        "taken_action": None,
        "notes": None,
    }
    base.update(overrides)
    return base


class TestSaveEndpoint:
    def test_save_returns_201_with_id(self, client):
        res = client.post("/api/hands", json=_sample_payload())
        assert res.status_code == 201
        body = res.json()
        assert isinstance(body["id"], int)
        assert body["id"] > 0
        assert body["created_at"]
        assert body["suggestion"] == "raise"
        assert body["taken_action"] is None

    def test_save_with_action_and_notes(self, client):
        res = client.post(
            "/api/hands",
            json=_sample_payload(taken_action="call", notes="bom call"),
        )
        assert res.status_code == 201
        body = res.json()
        assert body["taken_action"] == "call"
        assert body["notes"] == "bom call"

    def test_save_with_invalid_action_returns_400(self, client):
        res = client.post(
            "/api/hands",
            json=_sample_payload(taken_action="shove-all-in"),
        )
        assert res.status_code == 400
        assert "Ação tomada inválida" in res.json()["detail"]

    def test_save_with_invalid_opponents_returns_422(self, client):
        res = client.post("/api/hands", json=_sample_payload(num_opponents=0))
        assert res.status_code == 422


class TestListEndpoint:
    def test_list_empty(self, client):
        res = client.get("/api/hands")
        assert res.status_code == 200
        body = res.json()
        assert body["items"] == []
        assert body["total"] == 0
        assert body["limit"] == 50
        assert body["offset"] == 0

    def test_list_most_recent_first(self, client):
        ids = []
        for note in ("um", "dois", "três"):
            res = client.post("/api/hands", json=_sample_payload(notes=note))
            ids.append(res.json()["id"])

        listed = client.get("/api/hands").json()
        assert listed["total"] == 3
        # Most recent first → reverse of insertion order.
        assert [h["id"] for h in listed["items"]] == list(reversed(ids))

    def test_list_pagination(self, client):
        for i in range(5):
            client.post("/api/hands", json=_sample_payload(notes=f"hand{i}"))
        page1 = client.get("/api/hands?limit=2&offset=0").json()
        page2 = client.get("/api/hands?limit=2&offset=2").json()
        page3 = client.get("/api/hands?limit=2&offset=4").json()
        assert page1["total"] == 5
        assert len(page1["items"]) == 2
        assert len(page2["items"]) == 2
        assert len(page3["items"]) == 1
        ids_seen = {h["id"] for h in page1["items"] + page2["items"] + page3["items"]}
        assert len(ids_seen) == 5

    def test_list_rejects_invalid_pagination(self, client):
        assert client.get("/api/hands?limit=0").status_code == 422
        assert client.get("/api/hands?offset=-1").status_code == 422


class TestGetEndpoint:
    def test_get_existing(self, client):
        created = client.post("/api/hands", json=_sample_payload()).json()
        res = client.get(f"/api/hands/{created['id']}")
        assert res.status_code == 200
        assert res.json()["id"] == created["id"]

    def test_get_missing_returns_404(self, client):
        res = client.get("/api/hands/99999")
        assert res.status_code == 404
        assert res.json()["detail"] == "Mão não encontrada."


class TestDeleteEndpoint:
    def test_delete_existing_returns_204(self, client):
        created = client.post("/api/hands", json=_sample_payload()).json()
        res = client.delete(f"/api/hands/{created['id']}")
        assert res.status_code == 204
        # And it really is gone.
        assert client.get(f"/api/hands/{created['id']}").status_code == 404

    def test_delete_missing_returns_404(self, client):
        res = client.delete("/api/hands/77777")
        assert res.status_code == 404


class TestNullableFieldsRoundtrip:
    """Regression guard for a frontend bug: rendering crashed when an item
    came back with `taken_action: null`. The backend must keep serializing
    those nulls explicitly so the frontend can rely on the contract."""

    def test_list_returns_explicit_null_for_missing_taken_action(self, client):
        client.post("/api/hands", json=_sample_payload(taken_action=None, notes=None))
        body = client.get("/api/hands").json()

        assert body["total"] == 1
        item = body["items"][0]
        assert "taken_action" in item, "taken_action key must always be present"
        assert item["taken_action"] is None
        assert "notes" in item
        assert item["notes"] is None
        # suggestion is required by the schema — never null.
        assert isinstance(item["suggestion"], str) and item["suggestion"]

    def test_list_returns_total_even_when_paginated_to_empty_page(self, client):
        for _ in range(3):
            client.post("/api/hands", json=_sample_payload())
        body = client.get("/api/hands?limit=10&offset=10").json()
        assert body["items"] == []
        assert body["total"] == 3  # frontend uses this to render the counter

    def test_list_mixes_rows_with_and_without_taken_action(self, client):
        client.post("/api/hands", json=_sample_payload(taken_action="call"))
        client.post("/api/hands", json=_sample_payload(taken_action=None))
        client.post("/api/hands", json=_sample_payload(taken_action="raise"))
        items = client.get("/api/hands").json()["items"]
        actions = [it["taken_action"] for it in items]
        assert None in actions
        assert "call" in actions
        assert "raise" in actions


def test_isolation_between_tests_via_dependency_override(tmp_path):
    """Sanity check: two independent TestClient sessions don't see each other's data."""
    repo_a = HandRepository(tmp_path / "a.db")
    repo_b = HandRepository(tmp_path / "b.db")

    app.dependency_overrides[get_repository] = lambda: repo_a
    try:
        client_a = TestClient(app)
        client_a.post("/api/hands", json=_sample_payload(notes="from-a"))
        assert client_a.get("/api/hands").json()["total"] == 1
    finally:
        app.dependency_overrides.pop(get_repository, None)

    app.dependency_overrides[get_repository] = lambda: repo_b
    try:
        client_b = TestClient(app)
        assert client_b.get("/api/hands").json()["total"] == 0
    finally:
        app.dependency_overrides.pop(get_repository, None)
