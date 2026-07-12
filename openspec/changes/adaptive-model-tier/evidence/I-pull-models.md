# Evidence — pull-models.sh + adaptive tier resolver flip

- **Change**: `adaptive-model-tier`
- **Scope**: operational verification of `docs/plan/SESSION-HANDOFF.md` "Immediate next steps" step 1 — pull the 2026 model stack and prove the tier resolver flips `primary` to `qwen3.5:4b` with zero config edits. Not a code iteration; no source files modified.
- **Date**: 2026-07-12
- **Git HEAD**: `846f5499d75bd2e4fb01c308ba49d4de7d0b5677` (branch `change/phase0-foundation`)
- **Machine**: Hackintosh, Ryzen 5 5600G, 16 GB RAM, RX 570 (CPU-only inference), Ollama at `127.0.0.1:11434`

## Dual validation sources

1. **Source 1 — Ollama registry probe**: `curl -s http://127.0.0.1:11434/api/tags`
2. **Source 2 — resolver profile**: `shared/model_tier.py` `TierResolver.resolve()` via `get_resolver().force_refresh()`

Both probed BEFORE and AFTER the pull; they agree (model appears in Ollama tags AND resolver picks it as `primary`).

## Step 1 — BEFORE state

### Command: `curl -s http://127.0.0.1:11434/api/tags` (exit 0)

```json
{"models":[{"name":"bge-m3:latest", ...},{"name":"qwen2.5:7b", ...},{"name":"openchat:7b-v3.5-q4_K_S", ...},{"name":"llama3.1:8b", ...},{"name":"deepseek-r1:14b", ...},{"name":"phi4-mini:latest", ...}]}
```

Full model name list before pull: `bge-m3:latest`, `qwen2.5:7b`, `openchat:7b-v3.5-q4_K_S`, `llama3.1:8b`, `deepseek-r1:14b`, `phi4-mini:latest`. **No `qwen3.5:*` or `qwen3-embedding:*` present.**

### Command: `PYTHONPATH=src MEMORY_SERVER_DIR=/Users/manu/MCP-servers/MCP-agent-memory .venv/bin/python -c "from shared.model_tier import get_resolver; p = get_resolver().force_refresh(); print(p.tier); print(p)"` (exit 0)

```
T2
schema_version='1.0' probed_at='2026-07-12T01:28:55.007546+00:00' hostname='Mac-Pro-de-manu.local' os='darwin' arch='x86_64' cpu='AMD Ryzen 5 5600G with Radeon Graphics' logical_cores=12 ram_total_gb=16.0 ram_available_gb=6.58 gpu_class='none' backends=BackendMap(ollama=BackendStatus(reachable=True, url='http://127.0.0.1:11434', detail=None), llama_server=BackendStatus(reachable=False, url='http://127.0.0.1:8080', detail='ConnectError'), llama_cpp_local=BackendStatus(reachable=False, url=None, detail='engine/bin/llama-server missing')) models_available=['bge-m3:latest', 'qwen2.5:7b', 'openchat:7b-v3.5-q4_K_S', 'llama3.1:8b', 'deepseek-r1:14b', 'phi4-mini:latest'] tier='T2' tier_reason='standard: 6.58 GB available / 16 GB total; primary degraded to qwen2.5:7b: qwen3.5:4b not in ollama tags (run install/pull-models.sh)' role_models=RoleModels(embedding='qwen3-embedding:0.6b', reranker='qwen3-reranker:0.6b', small='qwen3.5:2b', primary='qwen2.5:7b', coordinator=None)
```

**BEFORE**: tier `T2`, `role_models.primary = 'qwen2.5:7b'` (explicit degraded fallback — `tier_reason` states `primary degraded to qwen2.5:7b: qwen3.5:4b not in ollama tags`).

## Step 2 — run `install/pull-models.sh`

Ran in background (bash task id `bwccuqooa`) because the ~4.6 GB download exceeds the default 2-minute foreground timeout. Waited for actual completion notification (did not assume success from a timeout).

### Command: `bash install/pull-models.sh` — exit code `0`

Cleaned (ANSI progress spinners stripped) output:

```
==> Checking Ollama daemon at http://127.0.0.1:11434
==> Pulling qwen3.5:4b
success
==> Pulling qwen3.5:2b
success
==> Pulling qwen3-embedding:0.6b
success
==> Verifying pulled models against http://127.0.0.1:11434/api/tags
    ok: qwen3.5:4b
    ok: qwen3.5:2b
    ok: qwen3-embedding:0.6b
==> Done. Re-probe the tier with: curl -s http://127.0.0.1:8890/api/model-tier
```

All three models (`qwen3.5:4b`, `qwen3.5:2b`, `qwen3-embedding:0.6b`) pulled successfully and verified present in `/api/tags` by the script's own post-pull check.

## Step 3 — AFTER state

### Command: `curl -s http://127.0.0.1:11434/api/tags` (exit 0)

```json
{"models":[{"name":"qwen3-embedding:0.6b", ...},{"name":"qwen3.5:2b", ...},{"name":"qwen3.5:4b", ...},{"name":"bge-m3:latest", ...},{"name":"qwen2.5:7b", ...},{"name":"openchat:7b-v3.5-q4_K_S", ...},{"name":"llama3.1:8b", ...},{"name":"deepseek-r1:14b", ...},{"name":"phi4-mini:latest", ...}]}
```

Full model name list after pull: `qwen3-embedding:0.6b`, `qwen3.5:2b`, `qwen3.5:4b`, `bge-m3:latest`, `qwen2.5:7b`, `openchat:7b-v3.5-q4_K_S`, `llama3.1:8b`, `deepseek-r1:14b`, `phi4-mini:latest`. **All three new models present.**

### Command: `PYTHONPATH=src MEMORY_SERVER_DIR=/Users/manu/MCP-servers/MCP-agent-memory .venv/bin/python -c "from shared.model_tier import get_resolver; p = get_resolver().force_refresh(); print(p.tier); print(p)"` (exit 0)

```
T2
schema_version='1.0' probed_at='2026-07-12T01:30:54.594279+00:00' hostname='Mac-Pro-de-manu.local' os='darwin' arch='x86_64' cpu='AMD Ryzen 5 5600G with Radeon Graphics' logical_cores=12 ram_total_gb=16.0 ram_available_gb=6.72 gpu_class='none' backends=BackendMap(ollama=BackendStatus(reachable=True, url='http://127.0.0.1:11434', detail=None), llama_server=BackendStatus(reachable=False, url='http://127.0.0.1:8080', detail='ConnectError'), llama_cpp_local=BackendStatus(reachable=False, url=None, detail='engine/bin/llama-server missing')) models_available=['qwen3-embedding:0.6b', 'qwen3.5:2b', 'qwen3.5:4b', 'qwen2.5:7b', 'bge-m3:latest', 'openchat:7b-v3.5-q4_K_S', 'llama3.1:8b', 'deepseek-r1:14b', 'phi4-mini:latest'] tier='T2' tier_reason='standard: 6.72 GB available / 16 GB total' role_models=RoleModels(embedding='qwen3-embedding:0.6b', reranker='qwen3-reranker:0.6b', small='qwen3.5:2b', primary='qwen3.5:4b', coordinator=None)
```

**AFTER**: tier `T2` (unchanged, as expected — RAM class didn't change), `role_models.primary = 'qwen3.5:4b'` — flipped. `tier_reason` no longer mentions degradation; it's the plain "standard" message.

## Step 4 — Comparison

| Field | BEFORE | AFTER |
|---|---|---|
| `tier` | T2 | T2 (unchanged, correct — hardware unchanged) |
| `role_models.primary` | `qwen2.5:7b` (degraded fallback) | **`qwen3.5:4b`** (target per IMPROVEMENT-PLAN §3.5-bis) |
| `role_models.small` | `qwen3.5:2b` (already resolved — tag existed in the map before pull but model wasn't in Ollama; note: this value was already `qwen3.5:2b` pre-pull, meaning the resolver was already selecting it as target even though it hadn't been pulled yet — see caveat below) |
| `role_models.embedding` | `qwen3-embedding:0.6b` (same as above) |
| `tier_reason` | `... primary degraded to qwen2.5:7b: qwen3.5:4b not in ollama tags (run install/pull-models.sh)` | `standard: 6.72 GB available / 16 GB total` (no degradation note) |

**Config files touched: none.** No edits to `.env`, `shared/model_tier.py`, or any YAML/JSON config — confirmed by `git status --short` before and after showing only the pre-existing untracked `.bootstrap-status` and `tmp/` (present before this task started, unrelated to the model pull; `pull-models.sh` created no new tracked or untracked files itself).

**Caveat (dual-source cross-check note, not a discrepancy)**: `role_models.small` and `role_models.embedding` already showed `qwen3.5:2b` / `qwen3-embedding:0.6b` in the BEFORE probe even though those models were not yet in `ollama list` — i.e. the resolver's role→model map returns the *target* name for those roles regardless of availability (unlike `primary`, which has an explicit degraded-fallback branch to `qwen2.5:7b`). This is consistent with reading `shared/model_tier.py`'s degradation logic being primary-specific, not a bug — both sources (code path and live probe) agree once cross-checked; flagged here per §2 dual-validation for transparency, not as a blocker.

**Result: PASS.** The primary role model resolves to `qwen3.5:4b` after the pull with zero config changes, exactly as required by `docs/plan/IMPROVEMENT-PLAN.md` §3.5-bis.

## Commands + exit codes (summary)

| # | Command | Exit code |
|---|---|---|
| 1 | `curl -s http://127.0.0.1:11434/api/tags` (before) | 0 |
| 2 | `PYTHONPATH=src MEMORY_SERVER_DIR=... .venv/bin/python -c "..."` (before) | 0 |
| 3 | `bash install/pull-models.sh` | 0 |
| 4 | `curl -s http://127.0.0.1:11434/api/tags` (after) | 0 |
| 5 | `PYTHONPATH=src MEMORY_SERVER_DIR=... .venv/bin/python -c "..."` (after) | 0 |
