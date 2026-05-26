"""Central data contract for the engine.

The engine consumes a `GameState` and does not know where its data came from.
This keeps the door open for future input layers (OCR, hand history replay,
overlays) without touching the core.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Sequence

from treys import Card

VALID_RANKS = "23456789TJQKA"
VALID_SUITS = "shdc"
_CARD_PATTERN = re.compile(rf"^[{VALID_RANKS}][{VALID_SUITS}]$")
_VALID_BOARD_SIZES = {0, 3, 4, 5}


def parse_card(text: str) -> int:
    """Parse a single card string (e.g. 'As', 'Th', '2c') into a treys int.

    Tolerates whitespace and case; accepts '10x' as an alias for 'Tx'.
    Raises ValueError with the offending input on any malformed string.
    """
    if not isinstance(text, str):
        raise ValueError(f"Card must be a string, got {type(text).__name__}")

    cleaned = text.strip()
    if not cleaned:
        raise ValueError("Empty card string")

    # Common typo: '10h' instead of 'Th'.
    if len(cleaned) == 3 and cleaned[:2] == "10":
        cleaned = "T" + cleaned[2]

    if len(cleaned) != 2:
        raise ValueError(f"Invalid card format: {text!r} (expected rank+suit, e.g. 'As')")

    normalized = cleaned[0].upper() + cleaned[1].lower()
    if not _CARD_PATTERN.match(normalized):
        raise ValueError(
            f"Invalid card {text!r}: rank must be one of {VALID_RANKS}, "
            f"suit one of {VALID_SUITS}"
        )

    return Card.new(normalized)


def parse_cards(text: str) -> tuple[int, ...]:
    """Parse a whitespace- or comma-separated list of cards.

    Returns the tuple of treys card ints in input order.
    """
    if not text or not text.strip():
        return ()
    tokens = [t for t in re.split(r"[,\s]+", text.strip()) if t]
    return tuple(parse_card(t) for t in tokens)


@dataclass(frozen=True)
class GameState:
    """Immutable snapshot of a Texas Hold'em decision point.

    Attributes:
        hole_cards: Hero's two hole cards as treys card ints.
        board: 0, 3, 4 or 5 community card ints (preflop / flop / turn / river).
        pot: Current pot size before hero's action.
        to_call: Amount hero must put in to continue. 0 means hero can check.
        num_opponents: Active opponents still to be dealt with (1-8).
    """

    hole_cards: tuple[int, int]
    board: tuple[int, ...] = field(default_factory=tuple)
    pot: float = 0.0
    to_call: float = 0.0
    num_opponents: int = 1

    def __post_init__(self) -> None:
        if len(self.hole_cards) != 2:
            raise ValueError(f"Hero must have exactly 2 hole cards, got {len(self.hole_cards)}")

        if len(self.board) not in _VALID_BOARD_SIZES:
            raise ValueError(
                f"Board size must be one of {sorted(_VALID_BOARD_SIZES)}, "
                f"got {len(self.board)}"
            )

        all_cards = list(self.hole_cards) + list(self.board)
        if len(set(all_cards)) != len(all_cards):
            pretty = [Card.int_to_str(c) for c in all_cards]
            raise ValueError(f"Duplicate cards detected: {pretty}")

        if not 1 <= self.num_opponents <= 8:
            raise ValueError(f"num_opponents must be in 1..8, got {self.num_opponents}")

        if self.pot < 0:
            raise ValueError(f"pot must be non-negative, got {self.pot}")
        if self.to_call < 0:
            raise ValueError(f"to_call must be non-negative, got {self.to_call}")

    @property
    def street(self) -> str:
        """Street name derived from board size."""
        return {0: "preflop", 3: "flop", 4: "turn", 5: "river"}[len(self.board)]

    @property
    def known_cards(self) -> tuple[int, ...]:
        """All cards visible to hero (hole + board)."""
        return tuple(self.hole_cards) + tuple(self.board)
