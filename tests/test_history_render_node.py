"""Headless test that the history list renderer (app.js) doesn't throw.

Runs a Node script which loads `app.js` inside a vm context with a minimal
DOM stub and calls `buildHistoryItem` on a few realistic SavedHand payloads
(matching what `GET /api/hands` actually returns).

This catches frontend regressions like a helper being referenced but never
defined — the kind of bug a Python-only test suite can't see.

Skipped automatically when Node is not installed.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
SCRIPT = Path(__file__).parent / "_history_render_check.mjs"


@pytest.mark.skipif(NODE is None, reason="node not available")
def test_build_history_item_renders_real_payloads():
    """buildHistoryItem must handle the actual /api/hands response shape."""
    result = subprocess.run(
        [NODE, str(SCRIPT)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    # Surface stdout/stderr in the test report when something goes wrong.
    if result.returncode != 0:
        pytest.fail(
            "Renderização do histórico falhou no Node.\n"
            f"--- stdout ---\n{result.stdout}\n"
            f"--- stderr ---\n{result.stderr}"
        )
    # Sanity check: at least one OK line printed.
    assert "OK   " in result.stdout, result.stdout
