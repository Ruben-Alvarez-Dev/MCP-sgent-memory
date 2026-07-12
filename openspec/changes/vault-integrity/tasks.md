# Tasks — vault-integrity

Each item is one numbered iteration (`I01`, `I02`, …) per `openspec/AGENTS.md` §4: red test first, minimal green implementation, `tests/core` + `ruff` clean, evidence file, granular commit, box ticked — before the next item starts.

- [ ] 1. **Regex + filename format fix** — `bin/vault_processor.py`: correct `is_serialized()` to `^L\d+_[A-Z]+_\d{5}\.md$`; change `generate_name()` to emit `{layer}_{TYPE}_{seq:05d}.md` (drop timestamp + `_ES`/`_EN` suffix), matching `VaultManager._generate_vault_filename`.
      Tests: `is_serialized()` true for real generated names, false for the old broken pattern's inputs (documents the historical bug), false for junk; `generate_name()` output shape.

- [ ] 2. **Extract shared lock primitive** — move `VaultManager._acquire_lock`/`_release_lock` (`shared/vault_manager/__init__.py:744-805`) into a new `shared/vault_lock.py` (or fold into a new `shared/vault_counter.py`, see task 3) as standalone functions taking an explicit `lock_path`; `VaultManager` delegates to them (no behavior change).
      Tests: existing `tests/core/test_vault_manager.py` stays green unmodified (regression gate); new direct unit tests for the extracted lock (stale-lock steal after timeout with dead PID, wait-and-retry with live PID, atomic `O_EXCL` race between two callers).

- [ ] 3. **Locked + atomic counter** — new `shared/vault_counter.py::next_seq(vault_root: Path, layer: str) -> int` using the task-2 lock plus `tempfile.mkstemp` + `os.replace` for the `counter.json` write (never `Path.write_text` in place). `VaultManager._next_id` becomes a one-line delegate.
      Tests: single-caller correctness (1,2,3,… per layer); concurrency test (N threads or subprocesses hammering the same layer) asserts no duplicate sequence numbers and a well-formed `counter.json` at the end; crash-mid-write simulation (kill before `os.replace`) leaves the previous `counter.json` intact.

- [ ] 4. **Watcher adopts the shared counter** — `bin/vault_processor.py` deletes its own `get_next_seq` and calls `shared.vault_counter.next_seq`; delete the now-dead duplicate implementation.
      Tests: watcher-level test that two simulated concurrent watcher runs (or a watcher run racing a direct `VaultManager` call) against the same `counter.json` never collide.

- [ ] 5. **Single canonical `VAULT_PATH`** — add `resolve_vault_path()` to `shared/vault_constants.py` (default `data/Lx-persistent`); update `config.py`, `env_loader.py`'s default, `vault_manager/__init__.py`'s module-level fallback, and `bin/vault_processor.py` to all call it instead of hardcoding their own default. Align `install/app-install.sh`, `install/config.sh`, `scripts/generate-mcp-config.sh` defaults to the same value.
      Tests: a fixture that imports `config.py`, `env_loader.py`, and `vault_manager` fresh (subprocess or importlib reload to avoid module-cache bleed) with no `VAULT_PATH` set, asserts all three resolve to the identical absolute path; a second case with `VAULT_PATH` explicitly set asserts all three honor the override identically.

- [ ] 6. **ES/EN transactional mirror, honestly labeled** — `bin/vault_processor.py`: rename "EN copy"/translation language in logs, comments, docstrings to "EN mirror"; change the EN write from `shutil.copy2` to `tempfile.mkstemp` + `os.replace` into the destination; on mirror-write failure, do not advance/keep the counter increment for that item and do not leave the ES side marked complete — log at WARNING.
      Tests: happy path (both files land, byte-identical, single counter increment); fault-injection (mirror write raises mid-way) leaves zero partial files on disk and the failure is logged — assert via caplog/log capture, not print.

- [ ] 7. **One-shot path consolidation script** — new script (e.g. `scripts/consolidate-vault-path.py`) with `--dry-run` (default) and `--apply` modes: scans the non-canonical paths (`data/vault`, `<repo>/src/vault`) for `.md` files not already present in canonical `data/Lx-persistent`, reports what it would move, only writes on `--apply`, idempotent (safe to re-run), never invoked automatically.
      Tests: run against synthetic `tmp_path` fixtures (empty dirs, dirs with files, dirs with name collisions) — dry-run makes no filesystem changes; apply moves files and is a no-op on a second run.

- [ ] 8. **Regression + full-suite gate** — end-to-end test simulating the original bug end-to-end (old regex demonstrably never matches a real generated filename; new pipeline serializes a dropped note exactly once, no re-render on a second watcher pass over the same directory). Run full `tests/core` once, `ruff check src tests` clean.
      Evidence: red/green pairs for tasks 1-7 already captured per-iteration; this task's evidence is the full-suite green run + ruff clean run only.

- [ ] 9. **Spec reconciliation note** — once the Phase 1 baseline `openspec/specs/vault/` exists, diff this change's `specs/vault/spec.md` against it and convert to a proper ADDED/MODIFIED delta if needed before archiving. (No code change; tracking checkbox only — does not block archiving this change if the baseline still doesn't exist yet.)
