"""Made-hand evaluation, isolating the rest of the engine from treys' API.

If we ever swap out the evaluator, this is the only file that needs to change.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from treys import Card, Evaluator

_evaluator = Evaluator()


class HandCategory(Enum):
    """Made-hand categories ordered from weakest to strongest."""

    HIGH_CARD = "High Card"
    PAIR = "Pair"
    TWO_PAIR = "Two Pair"
    THREE_OF_A_KIND = "Three of a Kind"
    STRAIGHT = "Straight"
    FLUSH = "Flush"
    FULL_HOUSE = "Full House"
    FOUR_OF_A_KIND = "Four of a Kind"
    STRAIGHT_FLUSH = "Straight Flush"
    ROYAL_FLUSH = "Royal Flush"

    def beats(self, other: "HandCategory") -> bool:
        """True if self is strictly stronger than other."""
        order = list(HandCategory)
        return order.index(self) > order.index(other)


# treys.Evaluator.get_rank_class returns 0..9 (0 = Royal Flush, 9 = High Card).
_TREYS_CLASS_TO_CATEGORY: dict[int, HandCategory] = {
    0: HandCategory.ROYAL_FLUSH,
    1: HandCategory.STRAIGHT_FLUSH,
    2: HandCategory.FOUR_OF_A_KIND,
    3: HandCategory.FULL_HOUSE,
    4: HandCategory.FLUSH,
    5: HandCategory.STRAIGHT,
    6: HandCategory.THREE_OF_A_KIND,
    7: HandCategory.TWO_PAIR,
    8: HandCategory.PAIR,
    9: HandCategory.HIGH_CARD,
}


@dataclass(frozen=True)
class HandStrength:
    """Evaluated strength of hero's best 5-card hand.

    Attributes:
        score: treys score (1..7462, lower is better). 0 when undefined.
        category: human-readable category enum.
        label: pretty label (matches category.value except for royal flush).
        is_preflop: True if there is no community card yet.
    """

    score: int
    category: HandCategory
    label: str
    is_preflop: bool


def evaluate_hand(hole: Sequence[int], board: Sequence[int]) -> HandStrength:
    """Evaluate hero's best 5-card hand from hole + board.

    Preflop (board empty) cannot be evaluated as a made hand; we return a
    descriptive placeholder so callers can render something sensible.
    """
    if len(hole) != 2:
        raise ValueError(f"hole must have exactly 2 cards, got {len(hole)}")

    if len(board) == 0:
        return HandStrength(
            score=0,
            category=_preflop_category(hole),
            label=_preflop_label(hole),
            is_preflop=True,
        )

    if len(board) < 3:
        raise ValueError(f"board must have 0, 3, 4 or 5 cards, got {len(board)}")

    score = _evaluator.evaluate(list(board), list(hole))
    rank_class = _evaluator.get_rank_class(score)
    category = _TREYS_CLASS_TO_CATEGORY[rank_class]

    return HandStrength(
        score=score,
        category=category,
        label=category.value,
        is_preflop=False,
    )


def _preflop_category(hole: Sequence[int]) -> HandCategory:
    """Cheap preflop classifier: pair vs. high card. No real ranking."""
    ranks = [Card.get_rank_int(c) for c in hole]
    return HandCategory.PAIR if ranks[0] == ranks[1] else HandCategory.HIGH_CARD


def _preflop_label(hole: Sequence[int]) -> str:
    ranks = sorted((Card.get_rank_int(c) for c in hole), reverse=True)
    # treys ranks are 0..12 = 2..A. Map back to a printable rank char.
    rank_chars = "23456789TJQKA"
    a, b = rank_chars[ranks[0]], rank_chars[ranks[1]]
    if a == b:
        return f"Pocket {a}s (preflop)"
    suited = Card.get_suit_int(hole[0]) == Card.get_suit_int(hole[1])
    return f"{a}{b}{'s' if suited else 'o'} (preflop)"


def format_card(card: int) -> str:
    """Single-card string form, e.g. 'As'. Uses treys' canonical encoding."""
    return Card.int_to_str(card)


def format_cards(cards: Sequence[int]) -> str:
    """Whitespace-joined string of cards."""
    return " ".join(format_card(c) for c in cards)
