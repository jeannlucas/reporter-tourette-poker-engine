"""Tests for the POST /api/ocr endpoint with Ollama mocked out."""

from __future__ import annotations

import io
import json

import pytest
from fastapi.testclient import TestClient

from reporter_poker.web import ocr as ocr_module
from reporter_poker.web import server as server_module
from reporter_poker.web.server import app

client = TestClient(app)


def _png_bytes() -> bytes:
    """A 1x1 PNG (smallest valid image we can hand FastAPI)."""
    # Tiny opaque PNG generated offline.
    return bytes.fromhex(
        "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C4"
        "890000000D49444154789C636060606000000004000001B4F2A33E0000000049"
        "454E44AE426082"
    )


def _patch_ollama(monkeypatch, content: str) -> None:
    """Replace server_module.call_ollama with a stub returning `content`."""
    def fake(image_b64, **_kw):  # noqa: ARG001
        return content
    monkeypatch.setattr(server_module, "call_ollama", fake)


def test_ocr_happy_path(monkeypatch):
    _patch_ollama(monkeypatch, json.dumps({
        "hole_cards": ["As", "Kd"],
        "board": ["Qh", "Jc", "Th"],
        "pot": 200,
        "to_call": 50,
        "num_opponents": 2,
    }))

    files = {"image": ("hand.png", io.BytesIO(_png_bytes()), "image/png")}
    response = client.post("/api/ocr", files=files)

    assert response.status_code == 200
    body = response.json()
    assert body["hole_cards"] == ["As", "Kd"]
    assert body["board"] == ["Qh", "Jc", "Th"]
    assert body["pot"] == 200
    assert body["to_call"] == 50
    assert body["num_opponents"] == 2
    assert body["warnings"] == []


def test_ocr_invalid_card_is_flagged_not_500(monkeypatch):
    _patch_ollama(monkeypatch, json.dumps({
        "hole_cards": ["As", "XX"],  # XX invalid
        "board": [],
        "pot": None, "to_call": None, "num_opponents": None,
    }))

    files = {"image": ("hand.png", io.BytesIO(_png_bytes()), "image/png")}
    response = client.post("/api/ocr", files=files)

    assert response.status_code == 200
    body = response.json()
    assert body["hole_cards"] == ["As"]
    assert any("XX" in w for w in body["warnings"])


def test_ocr_ollama_unavailable_returns_503(monkeypatch):
    def fake(image_b64, **_kw):  # noqa: ARG001
        raise ocr_module.OcrUnavailable(
            "Não foi possível conectar ao Ollama local. Verifique se está rodando."
        )
    monkeypatch.setattr(server_module, "call_ollama", fake)

    files = {"image": ("hand.png", io.BytesIO(_png_bytes()), "image/png")}
    response = client.post("/api/ocr", files=files)

    assert response.status_code == 503
    assert "Ollama" in response.json()["detail"]


def test_ocr_bad_model_response_returns_502(monkeypatch):
    _patch_ollama(monkeypatch, "sorry I can't read this image")

    files = {"image": ("hand.png", io.BytesIO(_png_bytes()), "image/png")}
    response = client.post("/api/ocr", files=files)

    assert response.status_code == 502
    assert "JSON" in response.json()["detail"]


def test_ocr_empty_image_returns_400(monkeypatch):
    # Avoid hitting Ollama at all on empty image.
    _patch_ollama(monkeypatch, "{}")
    files = {"image": ("empty.png", io.BytesIO(b""), "image/png")}
    response = client.post("/api/ocr", files=files)
    assert response.status_code == 400


def test_ocr_missing_file_returns_422():
    response = client.post("/api/ocr")
    assert response.status_code == 422


def test_ocr_response_can_drive_analyze(monkeypatch):
    """The OCR output keys are compatible with the existing /api/analyze input."""
    _patch_ollama(monkeypatch, json.dumps({
        "hole_cards": ["As", "Ad"],
        "board": [],
        "pot": 100,
        "to_call": 50,
        "num_opponents": 1,
    }))

    files = {"image": ("hand.png", io.BytesIO(_png_bytes()), "image/png")}
    ocr_resp = client.post("/api/ocr", files=files).json()

    analyze = client.post("/api/analyze", json={
        "hole_cards": " ".join(ocr_resp["hole_cards"]),
        "board": " ".join(ocr_resp["board"]),
        "num_opponents": ocr_resp["num_opponents"],
        "pot": ocr_resp["pot"],
        "to_call": ocr_resp["to_call"],
        "iterations": 1000,
    })
    assert analyze.status_code == 200
    assert analyze.json()["hand"]["category"] == "PAIR"
