# Spec — vault

Status: current | Last-verified: 2026-07-12

> Source: `shared/vault_manager/__init__.py` (916 lines, `VaultManager` class, exposed via `L3_decisions_vault_*` MCP tools), `bin/vault_processor.py` (auto-serialization script), `bin/vault_watcher.sh` (shell trigger wrapper), `shared/config.py`.

## Capability: bilingual (ES/EN) Obsidian-compatible knowledge vault

Two independent code paths write to "the vault": `VaultManager` (atomic writes, backups, integrity checks, used by the `L3_decisions_vault_*` MCP tools) and the standalone `bin/vault_processor.py` script (auto-serialization + ES→EN sync, invoked by `bin/vault_watcher.sh`). They are **not the same implementation** and, as documented below, do not even agree on the vault's root path.

### Auto-serialization daemon status

`bin/vault_watcher.sh` is a shell wrapper meant to be triggered by `fswatch`, a cron poll, or manual invocation. **It is not registered as a `launchd` service** — README and ADR-0008 both confirm this auto-start integration is planned (Phase 3-bis) and not implemented. Today, nothing runs `vault_processor.py` unless a human or an external watcher does.

### Known defects (confirmed present, 2026-07-12 direct read)

- **P0-10 — serialization detector is permanently broken**: `bin/vault_processor.py:38`, `is_serialized()` uses the regex `r"^Ld+_[A-Z]+_d{8}Td{6}_d{5}_(ES|EN).md$"` — every `\d` was written as a literal `d`. This pattern can never match a real filename (`L3_DECISION_20260112T143022_00001_ES.md`), so **every already-serialized note is treated as unserialized on every run**: `process_unserialized()` re-serializes it under a new name, `get_next_seq()` increments `counter.json` again, and a fresh duplicate `_EN.md` copy is created each pass. Confirmed still present verbatim.
- **"EN translation" is a byte-for-byte copy, not a translation**: `process_unserialized()` (line 92) and `sync_edited()` (lines 110/114) both call `shutil.copy2(str(dest_path), str(en_path))` for the "EN" version — the EN file contains the original Spanish content unchanged. The README's "Generates English translation (if needed)" step (§ Auto-Serialization Daemon) does not correspond to any translation logic in this file.
- **Three divergent vault-root resolutions, still unreconciled**:
  1. `shared/config.py:94` → `Lx_persistent_path = os.getenv("VAULT_PATH", "<server_dir>/data/Lx-persistent")` (used by `unified/server/main.py` to create folders and by the `L3_decisions_vault_*` tools' `Config`).
  2. `shared/vault_manager/__init__.py:44-46` → `VAULT_PATH = os.getenv("VAULT_PATH", "<repo>/src/vault")` — same env var, **different default** than (1).
  3. `bin/vault_processor.py:6` → hardcoded absolute `~/MCP-servers/MCP-agent-memory/data/Lx-persistent`, ignoring `VAULT_PATH` entirely and breaking if the repo is cloned to a different path or a different user.
- **`counter.json` read-modify-write has no lock** in `vault_processor.py::get_next_seq()` (read → increment → write, no file lock) — concurrent invocations (e.g. watcher + manual run) can race and assign duplicate sequence numbers. `VaultManager` has its own `LOCKS_DIR`-based locking (`shared/vault_manager/__init__.py`), not shared with this script.

### Test coverage

No tests found exercising `bin/vault_processor.py`'s serialization/translation/orphan-cleanup logic.
