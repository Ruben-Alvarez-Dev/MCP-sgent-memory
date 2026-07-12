# Spec — vault (target end-state, self-contained)

> **Baseline note**: `openspec/specs/vault/` does not exist yet (Phase 1 governance baseline not landed). This file is written as a self-contained description of target behavior, not an ADDED/MODIFIED delta. Reconcile against the Phase 1 `vault` baseline once it lands (tracked as task 9 in this change's `tasks.md`); this does not block landing `vault-integrity`.

## Capability: vault (Obsidian-backed persistent notes)

The system SHALL maintain a single, human-readable, bilingual (ES authoring / EN mirror) note vault, backed by the filesystem, with deterministic serialization and crash-safe concurrent writes.

## ADDED Requirements

### Requirement: Single vault root

The system SHALL resolve the vault's filesystem root (`VAULT_PATH`) identically from every entrypoint that touches vault data (MCP server process, standalone watcher script, direct library import), from a single canonical resolver function, with one documented default.

#### Scenario: No override configured
- **WHEN** no `VAULT_PATH` environment variable is set
- **THEN** the MCP server (via `config.py`/`env_loader.py`), the standalone watcher (`bin/vault_processor.py`), and a bare `VaultManager` import all resolve to the same absolute path (`data/Lx-persistent` under the repo/install root)

#### Scenario: Override configured
- **WHEN** `VAULT_PATH` is set in the environment
- **THEN** all three resolution paths above honor the same overridden value, with no path silently falling back to a different default

### Requirement: Deterministic, idempotent serialization

The system SHALL classify and rename ("serialize") a human-authored note into the canonical filename grammar `L{layer}_{TYPE}_{seq:05d}.md` exactly once. A file already matching the canonical grammar SHALL be recognized as already serialized and SHALL NOT be re-processed.

#### Scenario: Fresh note dropped in Inbox
- **WHEN** a new `.md` file is placed in an ES-named vault folder and the watcher runs
- **THEN** the file is classified, renamed to the canonical grammar, and moved into its destination folder exactly once

#### Scenario: Already-serialized note, watcher runs again
- **WHEN** the watcher scans a folder containing a file already matching `L{layer}_{TYPE}_{seq:05d}.md`
- **THEN** the file is left untouched — no rename, no counter increment, no new mirror write

### Requirement: Locked, atomic sequence counter

The system SHALL allocate sequence numbers per memory layer from a single counter store (`counter.json`) via one shared implementation, protected by a mutual-exclusion lock across all writers, with crash-safe atomic file writes.

#### Scenario: Concurrent allocation
- **WHEN** two or more processes/threads request the next sequence number for the same layer at the same time
- **THEN** each caller receives a unique sequence number and no counter value is ever handed out twice

#### Scenario: Crash mid-write
- **WHEN** the process writing `counter.json` is interrupted before completing the write
- **THEN** the previously committed `counter.json` remains intact and readable (no truncated/corrupt JSON), because the write goes through a temp-file-plus-atomic-rename, never an in-place truncate

### Requirement: Honest, transactional ES/EN mirroring

The system SHALL mirror each Spanish-authored note verbatim into its English-named folder counterpart for structural/code-path compatibility, and SHALL NOT represent this mirror as a translation anywhere in code, logs, or documentation. The ES write and its EN mirror SHALL be treated as one transactional unit.

#### Scenario: Successful write
- **WHEN** a note is serialized
- **THEN** both the ES file and its EN mirror exist, are byte-identical, share the same canonical filename, and the sequence counter has been advanced exactly once for the pair

#### Scenario: Mirror write fails
- **WHEN** the EN mirror write fails partway through (disk full, permissions, crash)
- **THEN** no partially-written file is left on disk, the failure is logged at WARNING (never silently swallowed), and the pair is not considered complete (no dangling counter advance, no orphaned ES-only state presented as done)

### Requirement: No false translation claims

The system's code, logs, and documentation SHALL describe the EN-folder content as a mirror/copy of the Spanish original, never as a translation, unless and until a real translation mechanism is implemented (tracked as a separate future change).

#### Scenario: Reading the EN mirror
- **WHEN** any consumer (human or agent) reads a file from an English-named vault folder produced by this pipeline
- **THEN** nothing in that file's provenance metadata, surrounding logs, or code comments asserts the content has been translated
