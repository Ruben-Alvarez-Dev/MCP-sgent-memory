# Design: vault-integrity

## Context — what the code actually does today (verified by reading, not assumption)

| Component | File:line | Behavior |
|---|---|---|
| Watcher regex | `bin/vault_processor.py:38` | `re.match(r"^Ld+_[A-Z]+_d{8}Td{6}_d{5}_(ES\|EN).md$", filename)` — every `\d` lost its backslash. Matches zero real filenames. |
| Watcher counter | `bin/vault_processor.py:40-49` | `get_next_seq(layer)`: `json.loads` → increment → `Path.write_text`. No lock. |
| Watcher filename | `bin/vault_processor.py:51-56` | `{layer}_{TYPE}_{timestamp}_{seq:05d}_{lang}.md` (timestamp + ES/EN suffix). |
| Watcher ES/EN | `bin/vault_processor.py:83-93`, `97-117` | `shutil.move` (ES) then `shutil.copy2` (EN) — two independent filesystem ops, no rollback, byte-identical content. |
| Watcher vault root | `bin/vault_processor.py:6` | Hardcoded `~/MCP-servers/MCP-agent-memory/data/Lx-persistent`. Ignores `VAULT_PATH`. |
| VaultManager counter | `shared/vault_manager/__init__.py:653-665` | `_next_id(layer)`: same read-modify-write shape as the watcher's, independently implemented, also no lock. |
| VaultManager filename | `shared/vault_manager/__init__.py:667-679` | `{layer}_{TYPE}_{seq:05d}.md` — no timestamp, no lang suffix. Already tested (`tests/core/test_vault_manager.py::test_filename_generation`). |
| VaultManager lock | `shared/vault_manager/__init__.py:744-805` | `_acquire_lock`/`_release_lock`: atomic `O_CREAT\|O_EXCL` lock file, PID-liveness check, stale-lock stealing, used for note writes only — never for the counter. |
| VaultManager atomic write | `shared/vault_manager/__init__.py:189-205` | `tempfile.mkstemp` + `os.replace` for note content — never applied to `counter.json`, which is written with a direct `write_text`. |
| VaultManager vault root | `shared/vault_manager/__init__.py:44-46` | Module-level fallback `os.getenv("VAULT_PATH", <repo>/src/vault)`. |
| `env_loader.load_env()` | `shared/env_loader.py:126,132-134` | Sets `os.environ["VAULT_PATH"] = "<root>/data/vault"` **only if unset** — but every server entrypoint (`unified/server/main.py`, `L0_capture`, `L2_conversations`, `L3_decisions`, `L3_facts`, `L5_routing`, `Lx_reasoning`) calls `load_env()` at import time, before `config.py` is read. |
| `config.Config.from_env()` | `shared/config.py:94` | `Lx_persistent_path=os.getenv("VAULT_PATH", <root>/data/Lx-persistent)` — the `data/Lx-persistent` fallback is dead in practice because `env_loader` already set `VAULT_PATH=data/vault` first. |
| `config/mcp.json` | (repo root) | Does not set `VAULT_PATH` in the server's env block, so the above default chain runs unmodified in the real deployed server. |

Verified with `find data/vault data/Lx-persistent src/vault -name '*.md'`: only `data/Lx-persistent/README.md` exists; no user notes, no `counter.json`, anywhere. **No production data has been corrupted yet** — the bug is live but hasn't fired against real content. This lowers urgency for data recovery and raises urgency for landing the fix before real usage starts (the watcher and the MCP server are both already wired to run).

## Decision 1 — One filename grammar: adopt VaultManager's, retire the watcher's

**Chosen**: `L{layer}_{TYPE}_{seq:05d}.md`, no timestamp, no `_ES`/`_EN` suffix.

**Why not the other direction (make VaultManager match the watcher's timestamp+lang format)**: `VaultManager`'s format is already production-facing (used by every `write_note` call reachable from MCP tools) and covered by an existing green test. Changing it touches tested, live behavior for no benefit — the timestamp was never load-bearing (the counter alone guarantees uniqueness per layer, already the case in `VaultManager`) and the lang suffix goes away entirely once Decision 4 removes per-file duplication in favor of folder-based language separation (see below). Converging on the watcher's format instead would mean widening the class of things a "serialized" filename can be, which is the opposite of what a fixed regex should do.

**Consequence for `is_serialized()`**: `^L\d+_[A-Z]+_\d{5}\.md$` — a strict, narrow pattern matching the one grammar both writers now produce.

## Decision 2 — Canonical `VAULT_PATH`: `data/Lx-persistent`, resolved from one place

**Chosen default**: `data/Lx-persistent`. **Chosen source of truth**: extend `shared/vault_constants.py` (already documents itself as "SINGLE SOURCE OF TRUTH for the mapping") with a `resolve_vault_path(server_dir: str | None) -> Path` helper; every consumer (`config.py`, `env_loader.py`, `vault_manager/__init__.py`'s module fallback, `bin/vault_processor.py`) calls it instead of hardcoding a default.

**Why `data/Lx-persistent` over `data/vault` or `<repo>/vault`**:
- It matches the config field name (`Lx_persistent_path`) that already exists in `config.py` — the field was named after this directory, a strong signal of original intent that `env_loader.py`'s later `data/vault` default drifted away from.
- It is what the actively-scheduled watcher (`bin/vault_watcher.sh` → `bin/vault_processor.py`) already hardcodes; keeping the watcher's path and repointing the server is less disruptive than the reverse (the server has zero real content in either location today, verified above).
- `<repo>/src/vault` (VaultManager's bare-import fallback) puts runtime data inside the source tree — a packaging anti-pattern regardless of which of the other two wins; it must go either way.

**Migration**: since all three paths are currently empty of real notes (verified), no destructive merge is required for this change to be safe to land. Still building an explicit, dry-run-first, idempotent consolidation script (task I07) because: (a) it documents the resolution for anyone who *has* started writing to `data/vault` locally before this lands, (b) it is the kind of one-shot fixer this repo's own plan already uses as a pattern (`fix-embedding-truncation`'s poisoned-cache purge script), and (c) "nothing fake/seeded" and "reversible migrations" both argue for a real, tested script over a silent directory rename.

## Decision 3 — One locked, atomic counter (extracted, not duplicated)

**Chosen**: move `VaultManager._acquire_lock`/`_release_lock` (and the tempfile+`os.replace` write pattern already used for notes) into a small shared function, e.g. `shared/vault_counter.py::next_seq(vault_root, layer) -> int`. `VaultManager._next_id` becomes a one-line delegate; `bin/vault_processor.py` imports the same function and deletes its own `get_next_seq`.

**Why extraction over independently fixing both**: ADR-0007 requires "no duplication (extract, don't copy)". `VaultManager` already has a correct, tested lock primitive (PID-liveness, stale-lock stealing, atomic `O_EXCL` creation) — reimplementing a second locking scheme in the watcher (e.g. `fcntl.flock`) would reintroduce exactly the "two competing implementations" problem this change exists to close, just with a different bug shape. `fcntl` is also POSIX-only; the existing `O_EXCL`-file-based lock already works cross-platform (macOS today, Linux on other project machines per `CLAUDE.md`) with zero new dependencies — no ADR needed.

**Atomicity for the counter file itself**: lock prevents concurrent *writers*; it does not protect against a crash truncating `counter.json` mid-write. Apply the same `tempfile.mkstemp(dir=…) + os.replace` pattern `VaultManager` already uses for notes (`__init__.py:189-205`) to the counter write, closing that separately from the lock.

## Decision 4 — ES/EN semantics: explicit mirror, not translation

This is the one genuine either/or the task calls out, so the alternatives are laid out explicitly.

**Option A — Real transactional translation.** Call an LLM (now feasible via `ollama-backend`) to produce actual English content, written transactionally alongside the Spanish original. Rejected *for this change*: it adds a network call, latency, and a new failure mode (LLM down/slow) to every single vault write, which is exactly the kind of "silent degradation" surface `AGENTS.md` §1 warns about, and it needs its own cost/quality/prompt design — scope far beyond a P0 bugfix batch. Flagged as a legitimate future change (`vault-real-translation` or similar), sequenced after `model-stack-2026`.

**Option B — Explicit documented copy semantics (chosen).** Keep the mirror (VaultManager and the rest of the code already exclusively read/write the English-named folders — removing the mirror would break that dependency), but make it honest and safe:
- Rename every place this operation is named/logged from "EN copy"/"translation" to **"EN mirror"** (code comments, log lines, docstrings) — the content is verbatim Spanish; the folder name is a routing label, not a language claim.
- Make the pair transactional: write the EN mirror via `tempfile.mkstemp` + `os.replace` (matching the ES write's own atomicity, not a plain `shutil.copy2` straight onto the destination path); if the mirror write fails, delete the (already atomically placed) ES file's move-in-progress state or leave the ES file in place but do **not** advance the counter or mark the pair complete, and log at WARNING. No half-written pair should ever be observable by a reader.
- Drop the per-file `_ES`/`_EN` filename suffix (subsumed by Decision 1) — the two folders (Spanish-named for Obsidian, English-named for code) already carry the language distinction; a same-named file in both is unambiguous and removes the suffix-matching surface that caused the duplicate-file bug in the first place.

**Why B over "just leave it as an undocumented copy"**: the P1 finding is specifically that the current copy is *mislabeled* as a translation, which is actively worse than an honest copy — a future reader (or an LLM agent doing retrieval) trusting the "EN" folder gets Spanish text under a false premise. Documenting the real semantics costs nothing and closes that trust gap immediately, while leaving the door open to Option A later without another structural change (the transactional-pair mechanism from B is exactly what A would also need).

## Non-goals / explicitly deferred

- Real ES→EN translation (Decision 4, Option A) — future change.
- Hexagonal relocation of `vault_manager`/`vault_processor.py` into `domain/ports/adapters/app/runtime` — ADR-0007 sequences the `shared/` strangler migration to start at Phase 3 (`hexagonal-shared-split`); this Phase 2 bugfix intentionally stays flat in `shared/` so as not to conflate a data-integrity fix with an unrelated structural migration in the same review.
- Full merge/rebuild of `data/vault`/`src/vault` content — not needed, both are verified empty; the consolidation script (I07) is a safety net, not a data-rescue operation.

## Risks

- **Filename format change** could in principle break anything that pattern-matches the old watcher format. Grepped: nothing outside `bin/vault_processor.py` itself reads the `_ES`/`_EN`-suffixed pattern (confirmed via `grep -rn "_ES.md\|_EN.md"` — only hits in `vault_processor.py`), so the blast radius is contained to the one file being fixed.
- **Lock extraction** touches `VaultManager`'s tested write path indirectly (same lock primitive, now also used by the counter) — mitigated by keeping the existing `test_vault_manager.py` suite green as a hard gate per iteration (AGENTS.md §3) before adding new counter-specific tests.
