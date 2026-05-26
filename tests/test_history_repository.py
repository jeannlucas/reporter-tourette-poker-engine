"""Tests for the SQLite-backed hand history repository."""

from __future__ import annotations

import pytest

from reporter_poker.history import HandRepository, SavedHand


def _make_hand(**overrides) -> SavedHand:
    """Build a SavedHand with sensible defaults; override fields per test."""
    base = dict(
        hole_cards="As Ad",
        board="Kc 7h 2d",
        num_opponents=1,
        pot=100.0,
        to_call=50.0,
        street="flop",
        win_pct=88.4,
        tie_pct=0.2,
        loss_pct=11.4,
        iterations=25000,
        hand_category="PAIR",
        hand_label="Pair",
        is_preflop=False,
        outs_count=11,
        outs_cards="2s 2h 2c 7s 7d 7c Ks Kh Kd Ah Ac",
        next_card_improve_pct=23.4,
        required_equity_pct=33.33,
        ratio_str="2.0:1",
        is_plus_ev=True,
        edge_pct=55.07,
        suggestion="raise",
        taken_action=None,
        notes=None,
    )
    base.update(overrides)
    return SavedHand(**base)


@pytest.fixture
def repo(tmp_path):
    return HandRepository(tmp_path / "history.db")


class TestSaveAndGet:
    def test_save_assigns_id_and_timestamp(self, repo):
        saved = repo.save_hand(_make_hand())
        assert saved.id is not None
        assert saved.id > 0
        assert saved.created_at is not None
        assert "T" in saved.created_at  # ISO format

    def test_get_returns_full_record(self, repo):
        saved = repo.save_hand(_make_hand(taken_action="call", notes="bom call"))
        fetched = repo.get_hand(saved.id)
        assert fetched is not None
        assert fetched.id == saved.id
        assert fetched.hole_cards == "As Ad"
        assert fetched.board == "Kc 7h 2d"
        assert fetched.suggestion == "raise"
        assert fetched.taken_action == "call"
        assert fetched.notes == "bom call"
        assert fetched.is_plus_ev is True
        assert fetched.is_preflop is False

    def test_get_missing_returns_none(self, repo):
        assert repo.get_hand(99999) is None

    def test_optional_fields_roundtrip_none(self, repo):
        saved = repo.save_hand(_make_hand(
            next_card_improve_pct=None,
            required_equity_pct=None,
            taken_action=None,
            notes=None,
        ))
        fetched = repo.get_hand(saved.id)
        assert fetched.next_card_improve_pct is None
        assert fetched.required_equity_pct is None
        assert fetched.taken_action is None
        assert fetched.notes is None


class TestList:
    def test_empty(self, repo):
        rows, total = repo.list_hands()
        assert rows == []
        assert total == 0

    def test_orders_most_recent_first(self, repo):
        h1 = repo.save_hand(_make_hand(notes="first"))
        h2 = repo.save_hand(_make_hand(notes="second"))
        h3 = repo.save_hand(_make_hand(notes="third"))
        rows, total = repo.list_hands()
        assert total == 3
        # Most recent first → h3, h2, h1 (when timestamps tie, id DESC breaks tie)
        assert [r.notes for r in rows] == ["third", "second", "first"]
        assert [r.id for r in rows] == [h3.id, h2.id, h1.id]

    def test_pagination(self, repo):
        ids = [repo.save_hand(_make_hand(notes=f"n{i}")).id for i in range(7)]
        # most recent first → ids reversed
        expected = list(reversed(ids))

        page1, total = repo.list_hands(limit=3, offset=0)
        page2, _ = repo.list_hands(limit=3, offset=3)
        page3, _ = repo.list_hands(limit=3, offset=6)

        assert total == 7
        assert [r.id for r in page1] == expected[0:3]
        assert [r.id for r in page2] == expected[3:6]
        assert [r.id for r in page3] == expected[6:7]

    def test_negative_offset_raises(self, repo):
        with pytest.raises(ValueError):
            repo.list_hands(offset=-1)

    def test_non_positive_limit_raises(self, repo):
        with pytest.raises(ValueError):
            repo.list_hands(limit=0)


class TestDelete:
    def test_delete_existing_returns_true(self, repo):
        saved = repo.save_hand(_make_hand())
        assert repo.delete_hand(saved.id) is True
        assert repo.get_hand(saved.id) is None

    def test_delete_missing_returns_false(self, repo):
        assert repo.delete_hand(12345) is False

    def test_delete_only_affects_target_row(self, repo):
        a = repo.save_hand(_make_hand(notes="a"))
        b = repo.save_hand(_make_hand(notes="b"))
        c = repo.save_hand(_make_hand(notes="c"))
        repo.delete_hand(b.id)
        _, total = repo.list_hands()
        assert total == 2
        ids = {h.id for h in repo.list_hands()[0]}
        assert ids == {a.id, c.id}


class TestSchemaPersistence:
    def test_two_repositories_on_same_db_share_state(self, tmp_path):
        path = tmp_path / "shared.db"
        repo_a = HandRepository(path)
        saved = repo_a.save_hand(_make_hand(notes="persisted"))

        repo_b = HandRepository(path)
        fetched = repo_b.get_hand(saved.id)
        assert fetched is not None
        assert fetched.notes == "persisted"

    def test_parent_directory_is_created(self, tmp_path):
        nested = tmp_path / "deep" / "nest" / "history.db"
        HandRepository(nested)
        assert nested.parent.exists()
