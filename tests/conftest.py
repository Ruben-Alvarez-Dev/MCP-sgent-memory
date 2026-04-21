"""Shared fixtures and configuration for all tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure src/ is importable for all tests
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


# ── Shared project fixtures ───────────────────────────────────────


@pytest.fixture
def temp_project(tmp_path: Path) -> Path:
    """A minimal Python+TS project with known symbols for code map tests."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "service.py").write_text(
        "import os\nfrom datetime import datetime\n\n"
        "class AuthService:\n"
        "    def __init__(self, secret: str):\n"
        "        self.secret = secret\n\n"
        "    def get_token(self, user_id: int) -> str:\n"
        '        return f"{user_id}:{self.secret}"\n\n'
        "async def main_task():\n"
        '    print("Doing async work")\n'
    )
    (tmp_path / "src" / "api.ts").write_text(
        "import { HttpClient } from './http';\n\n"
        "export class ApiClient {\n"
        "    constructor(private http: HttpClient) {}\n\n"
        "    async fetchData(id: string): Promise<any> {\n"
        "        return this.http.get(`/data/${id}`);\n"
        "    }\n}\n\n"
        "function globalHelper(): void {\n"
        "    console.log('Helper');\n"
        "}\n"
    )
    (tmp_path / "src" / "empty.js").write_text("")
    (tmp_path / "src" / "config.weird").write_text("key=value")
    return tmp_path


@pytest.fixture
def temp_git_repo(tmp_path: Path) -> Path:
    """A minimal git repo with one commit, for worktree tests."""
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    (repo / "initial.txt").write_text("init")
    subprocess.run(["git", "add", "initial.txt"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@test.com", "commit", "-m", "init"],
        cwd=repo, check=True, capture_output=True,
    )
    return repo


@pytest.fixture
def noop_embed():
    """Return a deterministic embed_fn that produces 1024-dim zero vectors."""
    from shared.embedding import EMBEDDING_DIM

    def _embed(text: str) -> list[float]:
        return [0.0] * EMBEDDING_DIM

    return _embed
