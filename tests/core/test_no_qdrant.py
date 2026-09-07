"""Regression test promised by GATE_M2 (ISO-08) — no Qdrant may return.

GATE_M2 cited this file before it existed (audit finding 2026-09-06):
the demolition grep was run manually but never encoded as a test. This
closes that gap permanently.

Allowed residuals (documented in GATE_M2):
- positional parameter name `target_qdrant` (signature compatibility)
- legacy config field/env name `qdrant_collection`/`QDRANT_COLLECTION`
- inert directory-name exclusion string in code_map.py
"""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"

_ALLOWED_LINE_PATTERNS = [
    re.compile(r"target_qdrant"),                     # positional param name (compat)
    re.compile(r"qdrant_collection", re.IGNORECASE),  # legacy env/field/const name
    re.compile(r"#.*[Qq]drant"),                      # comments
    re.compile(r"['\"]qdrant['\"]"),                  # inert dir-name exclusion strings
    # historical/legacy context in docstrings (parity, demolition notes):
    re.compile(
        r"[Qq]drant[^\n]*(parity|legacy|compatible|was |was\b|replaces|replaced|"
        r"demolis|old |gone| demol|deleted|removed)", re.IGNORECASE
    ),
    re.compile(r"(parity|legacy|demolis|replaces|replaced|old|gone)[^\n]*[Qq]drant", re.IGNORECASE),
]


def _iter_py_files():
    yield from sorted(SRC.rglob("*.py"))


def test_no_live_qdrant_references_in_src():
    """ISO-08 regression: zero live Qdrant code references in src/."""
    offenders = []
    for path in _iter_py_files():
        if "__pycache__" in path.parts:
            continue
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            if "qdrant" not in line.lower():
                continue
            if any(pat.search(line) for pat in _ALLOWED_LINE_PATTERNS):
                continue
            offenders.append(f"{path.relative_to(SRC.parent)}:{lineno}: {line.strip()}")
    assert not offenders, "live Qdrant references survived:\n" + "\n".join(offenders)


def test_qdrant_client_modules_are_gone():
    """The demolished client modules must not reappear."""
    gone = [
        "shared/qdrant_client.py",
        "shared/qdrant_factory.py",
        "shared/scoped_qdrant.py",
        "shared/hybrid_qdrant.py",
        "retrieval/index_repo.py",
        "unified/server/main_http.py",
        "unified/server/backpack.py",
    ]
    for rel in gone:
        assert not (SRC / rel).exists(), f"demolished module reappeared: {rel}"
