"""FastAPI server exposing the engine to a local web UI.

This module is a thin transport layer. It validates the request payload,
builds a `GameState`, calls the engine's public functions, and shapes the
result into JSON. No game logic lives here.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..equity import count_outs, simulate_equity
from ..game_state import GameState, parse_cards
from ..hand_evaluator import evaluate_hand, format_card
from ..history import HandRepository, SavedHand
from ..pot_odds import compute_pot_odds, suggest_action
from .ocr import (
    OcrBadResponse,
    OcrUnavailable,
    call_ollama,
    parse_ocr_response,
)

MAX_OCR_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB

DEFAULT_DB_PATH = Path(os.environ.get("REPORTER_DB_PATH", "data/history.db"))


class AnalyzeRequest(BaseModel):
    hole_cards: str = Field(..., description="Two cards, e.g. 'As Ad'")
    board: str = Field(default="", description="0, 3, 4 or 5 cards")
    num_opponents: int = Field(..., ge=1, le=8)
    pot: float = Field(default=0.0, ge=0)
    to_call: float = Field(default=0.0, ge=0)
    iterations: int = Field(default=25_000, ge=500, le=200_000)


app = FastAPI(title="Reporter Tourette Poker Engine", docs_url="/api/docs")

_STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    """Serve the single-page web UI."""
    return FileResponse(_STATIC_DIR / "index.html")


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest) -> dict:
    """Run the full engine pipeline and return a JSON-friendly payload."""
    try:
        hole = parse_cards(req.hole_cards)
        if len(hole) != 2:
            raise ValueError(
                f"hole_cards must contain exactly 2 cards (got {len(hole)})"
            )
        board = parse_cards(req.board)
        state = GameState(
            hole_cards=(hole[0], hole[1]),
            board=board,
            pot=req.pot,
            to_call=req.to_call,
            num_opponents=req.num_opponents,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    made = evaluate_hand(state.hole_cards, state.board)
    equity = simulate_equity(state, iterations=req.iterations)
    outs = count_outs(state)

    hero_equity = equity.win_pct + equity.tie_pct / 2.0
    odds = compute_pot_odds(state.pot, state.to_call, hero_equity)
    action = suggest_action(hero_equity, odds.required_equity_pct, state.to_call)

    return {
        "street": state.street,
        "hole_cards": [format_card(c) for c in state.hole_cards],
        "board": [format_card(c) for c in state.board],
        "hand": {
            "category": made.category.name,
            "category_label": made.category.value,
            "label": made.label,
            "is_preflop": made.is_preflop,
        },
        "equity": {
            "win_pct": equity.win_pct,
            "tie_pct": equity.tie_pct,
            "loss_pct": equity.loss_pct,
            "iterations": equity.iterations,
            "hero_pct": hero_equity,
        },
        "outs": {
            "count": len(outs.outs),
            "cards": [format_card(c) for c in outs.outs],
            "next_card_improve_pct": outs.next_card_improve_pct,
            "current_category": outs.current_category.name,
        },
        "pot_odds": {
            "required_equity_pct": odds.required_equity_pct,
            "ratio_str": odds.ratio_str,
            "is_plus_ev": odds.is_plus_ev,
            "edge_pct": odds.edge_pct,
        },
        "suggestion": action,
    }


_default_repository: Optional[HandRepository] = None


def get_repository() -> HandRepository:
    """FastAPI dependency: lazy singleton repository pointing at DEFAULT_DB_PATH.

    Tests override this via `app.dependency_overrides[get_repository]` so they
    can point at a temporary database without touching the real one.
    """
    global _default_repository
    if _default_repository is None:
        _default_repository = HandRepository(DEFAULT_DB_PATH)
    return _default_repository


VALID_TAKEN_ACTIONS = {"fold", "call", "raise", "check", "bet"}


class SaveHandRequest(BaseModel):
    # Inputs
    hole_cards: str
    board: str = ""
    num_opponents: int = Field(..., ge=1, le=8)
    pot: float = Field(default=0.0, ge=0)
    to_call: float = Field(default=0.0, ge=0)

    # Result snapshot
    street: str
    win_pct: float
    tie_pct: float
    loss_pct: float
    iterations: int
    hand_category: str
    hand_label: str
    is_preflop: bool
    outs_count: int = 0
    outs_cards: str = ""
    next_card_improve_pct: Optional[float] = None
    required_equity_pct: Optional[float] = None
    ratio_str: str = ""
    is_plus_ev: bool
    edge_pct: float
    suggestion: str

    # User annotations
    taken_action: Optional[str] = None
    notes: Optional[str] = None


def _serialize(hand: SavedHand) -> dict:
    return hand.to_dict()


@app.post("/api/hands", status_code=201)
def save_hand_endpoint(
    req: SaveHandRequest,
    repo: HandRepository = Depends(get_repository),
) -> dict:
    """Persist a hand analysis snapshot for later study."""
    if req.taken_action is not None and req.taken_action not in VALID_TAKEN_ACTIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Ação tomada inválida: {req.taken_action!r}. "
                f"Use uma de: {sorted(VALID_TAKEN_ACTIONS)}."
            ),
        )
    hand = SavedHand(
        hole_cards=req.hole_cards,
        board=req.board,
        num_opponents=req.num_opponents,
        pot=req.pot,
        to_call=req.to_call,
        street=req.street,
        win_pct=req.win_pct,
        tie_pct=req.tie_pct,
        loss_pct=req.loss_pct,
        iterations=req.iterations,
        hand_category=req.hand_category,
        hand_label=req.hand_label,
        is_preflop=req.is_preflop,
        outs_count=req.outs_count,
        outs_cards=req.outs_cards,
        next_card_improve_pct=req.next_card_improve_pct,
        required_equity_pct=req.required_equity_pct,
        ratio_str=req.ratio_str,
        is_plus_ev=req.is_plus_ev,
        edge_pct=req.edge_pct,
        suggestion=req.suggestion,
        taken_action=req.taken_action,
        notes=req.notes,
    )
    saved = repo.save_hand(hand)
    return _serialize(saved)


@app.get("/api/hands")
def list_hands_endpoint(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    repo: HandRepository = Depends(get_repository),
) -> dict:
    """List saved hands, most recent first."""
    rows, total = repo.list_hands(limit=limit, offset=offset)
    return {
        "items": [_serialize(h) for h in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/hands/{hand_id}")
def get_hand_endpoint(
    hand_id: int,
    repo: HandRepository = Depends(get_repository),
) -> dict:
    hand = repo.get_hand(hand_id)
    if hand is None:
        raise HTTPException(status_code=404, detail="Mão não encontrada.")
    return _serialize(hand)


@app.delete("/api/hands/{hand_id}", status_code=204)
def delete_hand_endpoint(
    hand_id: int,
    repo: HandRepository = Depends(get_repository),
) -> None:
    removed = repo.delete_hand(hand_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Mão não encontrada.")
    return None


@app.post("/api/ocr")
async def ocr(image: UploadFile = File(...)) -> dict:
    """Pre-fill the form by running OCR on an uploaded screenshot via Ollama.

    The response mirrors the shape the frontend uses to populate slots and
    scenario inputs; the user always confirms before analyzing.
    """
    image_bytes = await image.read()

    if not image_bytes:
        raise HTTPException(status_code=400, detail="Imagem vazia.")
    if len(image_bytes) > MAX_OCR_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Imagem maior que o limite de 10 MB.",
        )

    image_b64 = base64.b64encode(image_bytes).decode("ascii")

    try:
        content = call_ollama(image_b64)
        result = parse_ocr_response(content)
    except OcrUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    except OcrBadResponse as e:
        raise HTTPException(status_code=502, detail=str(e))

    return result.to_dict()
