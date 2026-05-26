"""SQLite persistence for saved hand analyses.

The rest of the app does not talk SQL directly — it only calls
`HandRepository.save_hand / list_hands / get_hand / delete_hand`. This keeps
the engine decoupled and makes swapping storage trivial later.

The schema is intentionally denormalized and column-rich: the columns most
useful for future aggregate statistics (`suggestion`, `taken_action`,
`is_plus_ev`, `edge_pct`, `win_pct`) are first-class fields so a stats screen
can query them without parsing blobs.
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ─── Data model ──────────────────────────────────────────────────────────────


@dataclass
class SavedHand:
    """Snapshot of one analyzed hand persisted to disk.

    `id` and `created_at` are filled by the repository on insert.
    """

    # Inputs
    hole_cards: str
    board: str
    num_opponents: int
    pot: float
    to_call: float

    # Result (snapshot of /api/analyze output)
    street: str
    win_pct: float
    tie_pct: float
    loss_pct: float
    iterations: int
    hand_category: str
    hand_label: str
    is_preflop: bool
    outs_count: int
    outs_cards: str
    next_card_improve_pct: Optional[float]
    required_equity_pct: Optional[float]
    ratio_str: str
    is_plus_ev: bool
    edge_pct: float
    suggestion: str

    # User-supplied annotations
    taken_action: Optional[str] = None
    notes: Optional[str] = None

    # Assigned by the repository
    id: Optional[int] = None
    created_at: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        # Convert booleans to actual JSON-friendly bools (asdict already does).
        return d


# ─── Schema ──────────────────────────────────────────────────────────────────


_SCHEMA = """
CREATE TABLE IF NOT EXISTS hands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,

    hole_cards TEXT NOT NULL,
    board TEXT NOT NULL DEFAULT '',
    num_opponents INTEGER NOT NULL,
    pot REAL NOT NULL DEFAULT 0,
    to_call REAL NOT NULL DEFAULT 0,

    street TEXT NOT NULL,
    win_pct REAL NOT NULL,
    tie_pct REAL NOT NULL,
    loss_pct REAL NOT NULL,
    iterations INTEGER NOT NULL,
    hand_category TEXT NOT NULL,
    hand_label TEXT NOT NULL,
    is_preflop INTEGER NOT NULL,
    outs_count INTEGER NOT NULL DEFAULT 0,
    outs_cards TEXT NOT NULL DEFAULT '',
    next_card_improve_pct REAL,

    required_equity_pct REAL,
    ratio_str TEXT NOT NULL DEFAULT '',
    is_plus_ev INTEGER NOT NULL,
    edge_pct REAL NOT NULL,
    suggestion TEXT NOT NULL,

    taken_action TEXT,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_hands_created_at ON hands(created_at DESC);
"""


_COLUMNS = (
    "id, created_at, "
    "hole_cards, board, num_opponents, pot, to_call, "
    "street, win_pct, tie_pct, loss_pct, iterations, "
    "hand_category, hand_label, is_preflop, "
    "outs_count, outs_cards, next_card_improve_pct, "
    "required_equity_pct, ratio_str, is_plus_ev, edge_pct, suggestion, "
    "taken_action, notes"
)


# ─── Repository ──────────────────────────────────────────────────────────────


class HandRepository:
    """Thin SQLite-backed repository for `SavedHand` records.

    A new connection is opened per call. SQLite handles that fine and it keeps
    threading concerns out of the picture — important for FastAPI where each
    request can land on a different thread.
    """

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    # ── internals ──

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    @staticmethod
    def _row_to_hand(row: sqlite3.Row) -> SavedHand:
        return SavedHand(
            id=row["id"],
            created_at=row["created_at"],
            hole_cards=row["hole_cards"],
            board=row["board"],
            num_opponents=row["num_opponents"],
            pot=row["pot"],
            to_call=row["to_call"],
            street=row["street"],
            win_pct=row["win_pct"],
            tie_pct=row["tie_pct"],
            loss_pct=row["loss_pct"],
            iterations=row["iterations"],
            hand_category=row["hand_category"],
            hand_label=row["hand_label"],
            is_preflop=bool(row["is_preflop"]),
            outs_count=row["outs_count"],
            outs_cards=row["outs_cards"],
            next_card_improve_pct=row["next_card_improve_pct"],
            required_equity_pct=row["required_equity_pct"],
            ratio_str=row["ratio_str"],
            is_plus_ev=bool(row["is_plus_ev"]),
            edge_pct=row["edge_pct"],
            suggestion=row["suggestion"],
            taken_action=row["taken_action"],
            notes=row["notes"],
        )

    # ── public API ──

    def save_hand(self, hand: SavedHand) -> SavedHand:
        """Insert a new hand, returning the same record with id/created_at set."""
        created_at = hand.created_at or datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        )
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO hands (
                    created_at,
                    hole_cards, board, num_opponents, pot, to_call,
                    street, win_pct, tie_pct, loss_pct, iterations,
                    hand_category, hand_label, is_preflop,
                    outs_count, outs_cards, next_card_improve_pct,
                    required_equity_pct, ratio_str, is_plus_ev, edge_pct, suggestion,
                    taken_action, notes
                ) VALUES (
                    ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?
                )
                """,
                (
                    created_at,
                    hand.hole_cards, hand.board, hand.num_opponents, hand.pot, hand.to_call,
                    hand.street, hand.win_pct, hand.tie_pct, hand.loss_pct, hand.iterations,
                    hand.hand_category, hand.hand_label, int(hand.is_preflop),
                    hand.outs_count, hand.outs_cards, hand.next_card_improve_pct,
                    hand.required_equity_pct, hand.ratio_str, int(hand.is_plus_ev),
                    hand.edge_pct, hand.suggestion,
                    hand.taken_action, hand.notes,
                ),
            )
            hand.id = cur.lastrowid
            hand.created_at = created_at
        return hand

    def list_hands(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[SavedHand], int]:
        """Return (rows, total). Most recent first."""
        if limit <= 0:
            raise ValueError("limit deve ser positivo")
        if offset < 0:
            raise ValueError("offset não pode ser negativo")
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) AS c FROM hands").fetchone()["c"]
            rows = conn.execute(
                f"SELECT {_COLUMNS} FROM hands "
                "ORDER BY datetime(created_at) DESC, id DESC "
                "LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [self._row_to_hand(r) for r in rows], total

    def get_hand(self, hand_id: int) -> Optional[SavedHand]:
        """Return the hand with that id, or None if it doesn't exist."""
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT {_COLUMNS} FROM hands WHERE id = ?",
                (hand_id,),
            ).fetchone()
        return self._row_to_hand(row) if row else None

    def delete_hand(self, hand_id: int) -> bool:
        """Delete the hand. Returns True if a row was removed, False otherwise."""
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM hands WHERE id = ?", (hand_id,))
            return cur.rowcount > 0
