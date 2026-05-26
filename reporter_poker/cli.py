"""Interactive CLI: type a hand street-by-street and read the analysis."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Callable

from .equity import OutsResult, count_outs, simulate_equity
from .game_state import GameState, parse_card, parse_cards
from .hand_evaluator import evaluate_hand, format_cards
from .pot_odds import compute_pot_odds, suggest_action


HELP_TEXT = """\
Commands (work at any prompt):
  n / new       restart the hand from scratch
  q / quit      exit
  sims N        set Monte Carlo iterations for next analyses (default 25000)
  ? / help      show this help

Card format: rank + suit, e.g. As (Ace of spades), Th (Ten of hearts), 2c.
Suits: s h d c. Ranks: 2 3 4 5 6 7 8 9 T J Q K A.
"""


class _Restart(Exception):
    """Raised internally to break out to the top of a new hand."""


class _Quit(Exception):
    """Raised internally to break out of the main loop."""


@dataclass
class Session:
    iterations: int = 25_000


def _prompt(session: Session, message: str) -> str:
    """Read one line, dispatching meta-commands (n, q, sims N, ?)."""
    while True:
        try:
            raw = input(message).strip()
        except EOFError:
            raise _Quit()

        if not raw:
            continue

        lowered = raw.lower()
        if lowered in {"q", "quit", "exit"}:
            raise _Quit()
        if lowered in {"n", "new"}:
            raise _Restart()
        if lowered in {"?", "help"}:
            print(HELP_TEXT)
            continue
        if lowered.startswith("sims "):
            try:
                n = int(lowered.split(None, 1)[1])
                if n <= 0:
                    raise ValueError
                session.iterations = n
                print(f"  iterations set to {n}")
            except ValueError:
                print("  sims: expected a positive integer (e.g. 'sims 50000')")
            continue

        return raw


def _ask_cards(session: Session, message: str, expected: int) -> tuple[int, ...]:
    while True:
        raw = _prompt(session, message)
        try:
            cards = parse_cards(raw)
        except ValueError as e:
            print(f"  ! {e}")
            continue
        if len(cards) != expected:
            print(f"  ! expected {expected} card(s), got {len(cards)}")
            continue
        return cards


def _ask_int(session: Session, message: str, lo: int, hi: int) -> int:
    while True:
        raw = _prompt(session, message)
        try:
            value = int(raw)
        except ValueError:
            print(f"  ! expected an integer in [{lo}, {hi}]")
            continue
        if not lo <= value <= hi:
            print(f"  ! value must be in [{lo}, {hi}]")
            continue
        return value


def _ask_float(session: Session, message: str, lo: float = 0.0) -> float:
    while True:
        raw = _prompt(session, message)
        try:
            value = float(raw)
        except ValueError:
            print("  ! expected a number")
            continue
        if value < lo:
            print(f"  ! value must be >= {lo}")
            continue
        return value


def _make_state(
    hole: tuple[int, ...],
    board: tuple[int, ...],
    pot: float,
    to_call: float,
    num_opponents: int,
) -> GameState | None:
    """Build the GameState, printing a friendly message on validation error."""
    try:
        return GameState(
            hole_cards=(hole[0], hole[1]),
            board=board,
            pot=pot,
            to_call=to_call,
            num_opponents=num_opponents,
        )
    except ValueError as e:
        print(f"  ! invalid game state: {e}")
        return None


def _print_analysis(state: GameState, iterations: int) -> None:
    print()
    print(f"  street     : {state.street}")
    print(f"  hole       : {format_cards(state.hole_cards)}")
    if state.board:
        print(f"  board      : {format_cards(state.board)}")

    made = evaluate_hand(state.hole_cards, state.board)
    print(f"  hand       : {made.label}")

    print(f"  simulating equity ({iterations} iterations vs {state.num_opponents} opp)...")
    eq = simulate_equity(state, iterations=iterations)
    print(
        f"  equity     : win {eq.win_pct:5.2f}%  "
        f"tie {eq.tie_pct:5.2f}%  loss {eq.loss_pct:5.2f}%"
    )

    if len(state.board) in (3, 4):
        outs: OutsResult = count_outs(state)
        if outs.outs:
            print(
                f"  outs       : {len(outs.outs)} "
                f"({format_cards(outs.outs)})"
            )
            print(f"  next card  : {outs.next_card_improve_pct:5.2f}% to improve category")
        else:
            print("  outs       : none that lift the category")

    hero_equity = eq.win_pct + eq.tie_pct / 2.0
    odds = compute_pot_odds(state.pot, state.to_call, hero_equity)
    print(
        f"  pot odds   : need {odds.required_equity_pct:5.2f}% "
        f"(ratio {odds.ratio_str})  edge {odds.edge_pct:+.2f}%"
    )
    action = suggest_action(hero_equity, odds.required_equity_pct, state.to_call)
    verdict = "+EV" if odds.is_plus_ev else "-EV"
    print(f"  suggestion : {action.upper()}  [{verdict} vs pot odds]")
    print()


def _run_hand(session: Session) -> None:
    print()
    print("=== new hand ===")
    hole = _ask_cards(session, "  hero hole cards (e.g. 'As Kd'): ", 2)
    num_opp = _ask_int(session, "  number of opponents (1-8): ", 1, 8)
    pot = _ask_float(session, "  current pot: ")
    to_call = _ask_float(session, "  amount to call (0 if free): ")

    state = _make_state(hole, (), pot, to_call, num_opp)
    if state is None:
        return
    _print_analysis(state, session.iterations)

    # Flop.
    flop = _ask_cards(session, "  flop (3 cards, or 'n' to restart): ", 3)
    pot = _ask_float(session, "  updated pot: ")
    to_call = _ask_float(session, "  amount to call: ")
    state = _make_state(hole, flop, pot, to_call, num_opp)
    if state is None:
        return
    _print_analysis(state, session.iterations)

    # Turn.
    turn = _ask_cards(session, "  turn (1 card): ", 1)
    pot = _ask_float(session, "  updated pot: ")
    to_call = _ask_float(session, "  amount to call: ")
    state = _make_state(hole, flop + turn, pot, to_call, num_opp)
    if state is None:
        return
    _print_analysis(state, session.iterations)

    # River.
    river = _ask_cards(session, "  river (1 card): ", 1)
    pot = _ask_float(session, "  updated pot: ")
    to_call = _ask_float(session, "  amount to call: ")
    state = _make_state(hole, flop + turn + river, pot, to_call, num_opp)
    if state is None:
        return
    _print_analysis(state, session.iterations)
    print("  (hand complete — type 'n' for a new hand or 'q' to quit)")
    _prompt(session, "  press enter, or 'n' / 'q': ")


def main() -> int:
    session = Session()
    print("Reporter Tourette Poker Engine — interactive CLI")
    print("Type '?' for help, 'q' to quit, 'n' to restart a hand.")
    while True:
        try:
            _run_hand(session)
        except _Restart:
            continue
        except _Quit:
            print("bye.")
            return 0
        except KeyboardInterrupt:
            print("\nbye.")
            return 0


if __name__ == "__main__":
    sys.exit(main())
