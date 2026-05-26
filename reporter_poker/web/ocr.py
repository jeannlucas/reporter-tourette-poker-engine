"""OCR layer that uses a local Ollama vision model to pre-fill the form.

This module is split from the FastAPI handler so the parsing/validation logic
can be tested without spinning up Ollama or the server.

Pipeline:
    image bytes  ─▶  call_ollama(image_b64)  ─▶  raw text from the model
                                             ─▶  parse_ocr_response(text)
                                             ─▶  OcrResult(...)

The HTTP call surface is intentionally tiny so it is easy to monkeypatch in
tests with a fake function.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from ..game_state import parse_card

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_VISION_MODEL", "qwen2.5vl")
OLLAMA_TIMEOUT_S = float(os.environ.get("OLLAMA_TIMEOUT_S", "90"))

OCR_PROMPT = """\
You are a Texas Hold'em screenshot reader. Inspect the image and extract:

- hole_cards: array of 0, 1 or 2 cards held by the HERO (the user's own hand)
- board: array of 0, 3, 4 or 5 community cards (flop, turn, river)
- pot: current pot amount as a number, or null if not visible
- to_call: amount the hero must pay to call, as a number, or null
- num_opponents: number of active opponents in the hand, or null

Each card is a 2-character string: rank + suit (lowercase suit).
Ranks: 2 3 4 5 6 7 8 9 T J Q K A   (T = ten)
Suits: s (spades), h (hearts), d (diamonds), c (clubs)
Examples: "As" (Ace of spades), "Th" (Ten of hearts), "2c" (Two of clubs).

Return ONLY a valid JSON object with exactly those five keys. No prose,
no markdown fences, no comments. Use null for scalars and [] for arrays
when a field cannot be determined.
"""


# ─── Errors ──────────────────────────────────────────────────────────────────


class OcrError(Exception):
    """Base error raised by the OCR layer for predictable failure modes."""


class OcrUnavailable(OcrError):
    """Ollama is unreachable / timed out / refused connection."""


class OcrBadResponse(OcrError):
    """Ollama answered but the response is not parseable JSON."""


# ─── Result type ─────────────────────────────────────────────────────────────


@dataclass
class OcrResult:
    """Normalized OCR output destined for the frontend."""

    hole_cards: list[str] = field(default_factory=list)
    board: list[str] = field(default_factory=list)
    pot: Optional[float] = None
    to_call: Optional[float] = None
    num_opponents: Optional[int] = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "hole_cards": self.hole_cards,
            "board": self.board,
            "pot": self.pot,
            "to_call": self.to_call,
            "num_opponents": self.num_opponents,
            "warnings": self.warnings,
        }


# ─── Ollama HTTP call ────────────────────────────────────────────────────────


def call_ollama(
    image_b64: str,
    *,
    host: str = None,
    model: str = None,
    timeout: float = None,
) -> str:
    """POST the image to Ollama's chat endpoint and return the message text.

    Raises OcrUnavailable if the daemon is not reachable / timed out.
    Raises OcrBadResponse if the HTTP status is non-200 or the body is broken.
    """
    host = host or OLLAMA_HOST
    model = model or OLLAMA_MODEL
    timeout = timeout if timeout is not None else OLLAMA_TIMEOUT_S

    url = f"{host.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": OCR_PROMPT,
                "images": [image_b64],
            }
        ],
        "options": {"temperature": 0.0},
    }

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=payload)
    except httpx.ConnectError as e:
        raise OcrUnavailable(
            "Não foi possível conectar ao Ollama local. Verifique se está rodando."
        ) from e
    except httpx.TimeoutException as e:
        raise OcrUnavailable(
            "Tempo esgotado falando com o Ollama. O modelo de visão pode estar carregando."
        ) from e
    except httpx.HTTPError as e:
        raise OcrUnavailable(f"Falha de rede com o Ollama: {e}") from e

    if resp.status_code != 200:
        raise OcrBadResponse(
            f"Ollama respondeu HTTP {resp.status_code}: {resp.text[:200]}"
        )

    try:
        data = resp.json()
    except ValueError as e:
        raise OcrBadResponse("Ollama não devolveu JSON válido.") from e

    content = (data.get("message") or {}).get("content", "")
    if not content:
        raise OcrBadResponse("Resposta do Ollama vazia.")
    return content


# ─── Parsing ─────────────────────────────────────────────────────────────────


def parse_ocr_response(content: str) -> OcrResult:
    """Extract a typed OcrResult from the model's raw text reply."""
    raw = _extract_json(content)

    result = OcrResult()
    result.hole_cards = _validate_cards(raw.get("hole_cards", []), "hole_cards", result.warnings)
    result.board = _validate_cards(raw.get("board", []), "board", result.warnings)
    result.pot = _to_amount(raw.get("pot"), "pot", result.warnings)
    result.to_call = _to_amount(raw.get("to_call"), "to_call", result.warnings)
    result.num_opponents = _to_opponents(raw.get("num_opponents"), result.warnings)

    if len(result.hole_cards) > 2:
        result.warnings.append(
            f"hole_cards com {len(result.hole_cards)} cartas — usando só as 2 primeiras."
        )
        result.hole_cards = result.hole_cards[:2]

    if len(result.board) not in (0, 3, 4, 5):
        result.warnings.append(
            f"board com {len(result.board)} cartas — não corresponde a flop/turn/river."
        )

    # Cross-duplicate check.
    all_cards = result.hole_cards + result.board
    if len(set(all_cards)) != len(all_cards):
        result.warnings.append("Há cartas repetidas entre mão e board — confira a leitura.")

    return result


def _extract_json(text: str) -> dict[str, Any]:
    """Return the first valid JSON object found inside the text."""
    text = (text or "").strip()
    if not text:
        raise OcrBadResponse("Resposta do modelo vazia.")

    # 1. Direct parse if the model behaved.
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # 2. Strip a ```json ... ``` (or ``` ... ```) code fence.
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        try:
            parsed = json.loads(fenced.group(1))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    # 3. Last resort: greedy slice between first { and last }.
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise OcrBadResponse("Resposta do modelo não contém JSON.")
    candidate = text[start : end + 1]
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as e:
        raise OcrBadResponse(f"JSON inválido na resposta do modelo: {e.msg}") from e
    if not isinstance(parsed, dict):
        raise OcrBadResponse("Resposta do modelo não é um objeto JSON.")
    return parsed


def _normalize_card(raw: str) -> str:
    """Return the canonical 2-char card string for a raw token."""
    cleaned = raw.strip()
    if len(cleaned) == 3 and cleaned[:2] == "10":
        cleaned = "T" + cleaned[2]
    return cleaned[0].upper() + cleaned[1].lower()


def _validate_cards(items: Any, field_name: str, warnings: list[str]) -> list[str]:
    """Filter out anything the engine wouldn't accept; warn for dropped entries."""
    if items is None:
        return []
    if not isinstance(items, list):
        warnings.append(f"{field_name} não é uma lista — ignorando.")
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for i, raw in enumerate(items):
        if not isinstance(raw, str):
            warnings.append(f"{field_name}[{i}] = {raw!r} não é texto.")
            continue
        try:
            parse_card(raw)
        except ValueError:
            warnings.append(f"{field_name}[{i}] = '{raw}' não reconhecida.")
            continue
        normalized = _normalize_card(raw)
        if normalized in seen:
            warnings.append(f"{field_name}[{i}] = '{raw}' duplicada — ignorando.")
            continue
        seen.add(normalized)
        cleaned.append(normalized)
    return cleaned


def _to_amount(value: Any, field_name: str, warnings: list[str]) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        warnings.append(f"{field_name} = {value!r} não numérico.")
        return None
    try:
        amount = float(value)
    except (TypeError, ValueError):
        warnings.append(f"{field_name} = {value!r} não numérico.")
        return None
    if amount < 0:
        warnings.append(f"{field_name} negativo ({amount}) — ignorando.")
        return None
    return amount


def _to_opponents(value: Any, warnings: list[str]) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        warnings.append(f"num_opponents = {value!r} inválido.")
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        warnings.append(f"num_opponents = {value!r} não numérico.")
        return None
    if not 1 <= n <= 8:
        warnings.append(f"num_opponents fora do intervalo 1-8 (recebido {n}).")
        return None
    return n
