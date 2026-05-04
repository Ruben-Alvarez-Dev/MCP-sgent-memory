"""Tests for VaultManager — the largest untested module (847 lines).

Uses tmp_path for isolation — no real vault data touched.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest
from shared.vault_manager import VaultManager
from shared.vault_constants import (
    FOLDER_INBOX, FOLDER_DECISIONS, FOLDER_KNOWLEDGE,
    FOLDER_EPISODES, FOLDER_ENTITIES, FOLDER_NOTES,
    FOLDER_PEOPLE, FOLDER_TEMPLATES,
)


@pytest.fixture
def vault(tmp_path: Path) -> VaultManager:
    """Create a VaultManager backed by a temp directory."""
    # Need to patch the module-level VAULT_PATH before instantiation
    import shared.vault_manager as vm
    original_path = vm.VAULT_PATH
    vm.VAULT_PATH = tmp_path
    # Also patch SYSTEM_DIR etc which depend on VAULT_PATH
    vm.SYSTEM_DIR = tmp_path / ".system"
    vm.BACKUPS_DIR = vm.SYSTEM_DIR / "backups"
    vm.LOCKS_DIR = vm.SYSTEM_DIR / "locks"
    vm.TRASH_DIR = vm.SYSTEM_DIR / "trash"
    vm.ORPHANED_DIR = vm.SYSTEM_DIR / "orphaned"
    vm.MANIFEST_PATH = vm.SYSTEM_DIR / "manifest.json"
    vm.CHECKSUMS_PATH = vm.SYSTEM_DIR / "checksums.json"
    vm.REPAIR_LOG = vm.SYSTEM_DIR / "repair_log.md"
    vm.INTEGRITY_REPORT = vm.SYSTEM_DIR / "integrity_report.md"

    v = VaultManager(Lx_persistent_path=tmp_path)
    yield v

    # Restore
    vm.VAULT_PATH = original_path
    vm.SYSTEM_DIR = original_path / ".system"
    vm.BACKUPS_DIR = vm.SYSTEM_DIR / "backups"
    vm.LOCKS_DIR = vm.SYSTEM_DIR / "locks"
    vm.TRASH_DIR = vm.SYSTEM_DIR / "trash"
    vm.ORPHANED_DIR = vm.SYSTEM_DIR / "orphaned"
    vm.MANIFEST_PATH = vm.SYSTEM_DIR / "manifest.json"
    vm.CHECKSUMS_PATH = vm.SYSTEM_DIR / "checksums.json"
    vm.REPAIR_LOG = vm.SYSTEM_DIR / "repair_log.md"
    vm.INTEGRITY_REPORT = vm.SYSTEM_DIR / "integrity_report.md"


# ── Structure ────────────────────────────────────────────────────────


class TestVaultStructure:
    def test_creates_all_folders(self, vault: VaultManager, tmp_path: Path):
        """VaultManager creates all required folders on init."""
        for folder in [FOLDER_INBOX, FOLDER_DECISIONS, FOLDER_KNOWLEDGE,
                       FOLDER_EPISODES, FOLDER_ENTITIES, FOLDER_NOTES,
                       FOLDER_PEOPLE, FOLDER_TEMPLATES]:
            assert (tmp_path / folder).is_dir(), f"Missing folder: {folder}"

    def test_creates_system_dirs(self, vault: VaultManager, tmp_path: Path):
        """System dirs (.system/backups, .system/locks, etc.) are created."""
        assert (tmp_path / ".system" / "backups").is_dir()
        assert (tmp_path / ".system" / "locks").is_dir()
        assert (tmp_path / ".system" / "trash").is_dir()


# ── write_note ──────────────────────────────────────────────────────


class TestWriteNote:
    def test_write_creates_file(self, vault: VaultManager, tmp_path: Path):
        """write_note creates a .md file in the specified folder."""
        dest = vault.write_note(FOLDER_DECISIONS, "test-decision.md", {
            "type": "decision",
            "content": "We chose to use hexagonal architecture.",
            "tags": ["architecture"],
        })
        assert dest.exists()
        assert dest.name == "test-decision.md"
        content = dest.read_text()
        assert "hexagonal architecture" in content
        assert "tags:" in content

    def test_write_adds_frontmatter(self, vault: VaultManager, tmp_path: Path):
        """Written notes have YAML frontmatter with type, date, author."""
        dest = vault.write_note(FOLDER_KNOWLEDGE, "pattern-test.md", {
            "type": "pattern",
            "content": "Always use dependency injection.",
        })
        fm = vault._read_frontmatter(dest)
        assert fm is not None
        assert fm["type"] == "pattern"
        assert "author" in fm
        assert "created" in fm

    def test_write_does_not_overwrite_human_note(self, vault: VaultManager, tmp_path: Path):
        """System write to a human-authored file creates a .system-note instead."""
        # Create a human-authored note
        dest = vault.write_note(FOLDER_DECISIONS, "my-decision.md", {
            "type": "decision",
            "content": "Human decision.",
        }, author="human")

        # System overwrite should create .system-note
        dest2 = vault.write_note(FOLDER_DECISIONS, "my-decision.md", {
            "type": "decision",
            "content": "System补充 note.",
        }, author="system")

        # Original human note should be untouched
        assert dest.read_text().startswith("---")
        assert "Human decision" in dest.read_text()

        # System note should exist as separate file
        assert dest2.name == "my-decision.system-note.md"
        assert "System" in dest2.read_text()

    def test_write_with_overwrite_flag(self, vault: VaultManager, tmp_path: Path):
        """allow_overwrite_human=True overwrites human notes."""
        dest = vault.write_note(FOLDER_DECISIONS, "over.md", {
            "type": "decision", "content": "v1",
        }, author="human")
        dest2 = vault.write_note(FOLDER_DECISIONS, "over.md", {
            "type": "decision", "content": "v2",
        }, author="system", allow_overwrite_human=True)
        assert "v2" in dest2.read_text()
        assert dest2.name == "over.md"

    def test_write_creates_backup(self, vault: VaultManager, tmp_path: Path):
        """Overwriting an existing file creates a backup."""
        dest = vault.write_note(FOLDER_NOTES, "backup-test.md", {
            "type": "note", "content": "original",
        })
        vault.write_note(FOLDER_NOTES, "backup-test.md", {
            "type": "note", "content": "updated",
        })
        # Check backup was created
        backups = list((tmp_path / ".system" / "backups").rglob("backup-test.md*"))
        assert len(backups) >= 1


# ── append_note ─────────────────────────────────────────────────────


class TestAppendNote:
    def test_append_to_existing(self, vault: VaultManager, tmp_path: Path):
        """append_note adds content after existing content."""
        vault.write_note(FOLDER_EPISODES, "session.md", {
            "type": "episode", "content": "Session started.",
        })
        dest = vault.append_note(FOLDER_EPISODES, "session.md", "Session ended.")
        content = dest.read_text()
        assert "Session started" in content
        assert "Session ended" in content

    def test_append_creates_if_missing(self, vault: VaultManager, tmp_path: Path):
        """append_note to non-existent file creates it."""
        dest = vault.append_note(FOLDER_NOTES, "new.md", "Fresh note.")
        assert dest.exists()
        assert "Fresh note" in dest.read_text()

    def test_append_creates_system_note_for_human_file(self, vault: VaultManager, tmp_path: Path):
        """Appending to human file creates .system-note."""
        vault.write_note(FOLDER_KNOWLEDGE, "learn.md", {
            "type": "pattern", "content": "Original thought.",
        }, author="human")
        dest = vault.append_note(FOLDER_KNOWLEDGE, "learn.md", "System addition.")
        assert dest.name == "learn.system-note.md"


# ── _classify_note ──────────────────────────────────────────────────


class TestClassifyNote:
    def test_decision_classification(self, vault: VaultManager):
        """Notes with decision keywords get classified as decisions."""
        result = vault._classify_note(
            "Decidimos usar hexagonal architecture. We chose ports and adapters. Hay que aislar dominio.",
            None,
        )
        assert result["type"] == "decision"
        assert result["folder"] == FOLDER_DECISIONS
        assert result["confidence"] == 0.8

    def test_episode_classification(self, vault: VaultManager):
        """Notes with session keywords get classified as episodes."""
        result = vault._classify_note(
            "Hoy hicimos refactor del installer. Session de debugging. Fixed los tests.",
            None,
        )
        assert result["type"] == "episode"
        assert result["folder"] == FOLDER_EPISODES

    def test_knowledge_classification(self, vault: VaultManager):
        """Notes with pattern keywords get classified as knowledge."""
        result = vault._classify_note(
            "Patrón observado: el patrón de repository aísla la BD. Aprendí que hay que usar interfaces. Tip: siembra interfaces.",
            None,
        )
        assert result["type"] == "pattern"
        assert result["folder"] == FOLDER_KNOWLEDGE

    def test_default_classification(self, vault: VaultManager):
        """Unclassifiable notes default to knowledge with low confidence."""
        result = vault._classify_note("Something random.", None)
        assert result["type"] == "note"
        assert result["folder"] == FOLDER_KNOWLEDGE
        assert result["confidence"] == 0.5

    def test_tag_extraction(self, vault: VaultManager):
        """Tech keywords in note body are extracted as tags."""
        result = vault._classify_note(
            "Decidimos usar JWT para auth. Hay que configurar qdrant. We chose docker.",
            None,
        )
        assert "auth" in result["tags"]
        assert "jwt" in result["tags"]
        assert "qdrant" in result["tags"]

    def test_filename_generation(self, vault: VaultManager):
        """_generate_filename creates a valid .md filename from body."""
        name = vault._generate_filename("Decidimos usar hexagonal architecture", FOLDER_DECISIONS)
        assert name.endswith(".md")
        assert len(name) <= 104
        assert "/" not in name


# ── integrity_check ─────────────────────────────────────────────────


class TestIntegrityCheck:
    def test_clean_vault_passes(self, vault: VaultManager, tmp_path: Path):
        """Fresh vault with no files passes integrity check."""
        vault.write_note(FOLDER_DECISIONS, "clean.md", {
            "type": "decision", "content": "Test decision.",
        })
        report = vault.integrity_check()
        assert report["files_found"] >= 1
        assert len(report["missing"]) == 0
        assert len(report["corrupted"]) == 0

    def test_missing_file_detected(self, vault: VaultManager, tmp_path: Path):
        """Integrity check detects files in manifest but missing on disk."""
        vault.write_note(FOLDER_NOTES, "to-delete.md", {
            "type": "note", "content": "Will be deleted.",
        })
        # Manually delete the file to simulate corruption
        note_path = tmp_path / FOLDER_NOTES / "to-delete.md"
        note_path.unlink()

        report = vault.integrity_check()
        assert "to-delete.md" in str(report["missing"]) or len(report["missing"]) > 0


# ── _read_frontmatter ───────────────────────────────────────────────


class TestReadFrontmatter:
    def test_reads_valid_frontmatter(self, vault: VaultManager, tmp_path: Path):
        """_read_frontmatter parses YAML frontmatter from markdown."""
        vault.write_note(FOLDER_DECISIONS, "fm-test.md", {
            "type": "decision",
            "content": "Body text here.",
            "tags": ["test"],
        })
        fm = vault._read_frontmatter(tmp_path / FOLDER_DECISIONS / "fm-test.md")
        assert fm is not None
        assert fm["type"] == "decision"
        assert fm["tags"] == ["test"]

    def test_returns_none_for_no_frontmatter(self, vault: VaultManager, tmp_path: Path):
        """_read_frontmatter returns None for files without frontmatter."""
        note = tmp_path / FOLDER_NOTES / "no-fm.md"
        note.parent.mkdir(parents=True, exist_ok=True)
        note.write_text("Just plain text, no frontmatter.")
        fm = vault._read_frontmatter(note)
        assert fm is None


# ── Folder mapping ──────────────────────────────────────────────────


class TestFolderMapping:
    def test_folder_map_consistency(self, vault: VaultManager):
        """FOLDER_MAP contains all expected folder constants."""
        expected_keys = [
            FOLDER_INBOX, FOLDER_DECISIONS, FOLDER_KNOWLEDGE,
            FOLDER_EPISODES, FOLDER_ENTITIES, FOLDER_NOTES,
            FOLDER_PEOPLE, FOLDER_TEMPLATES,
        ]
        for key in expected_keys:
            assert key in vault.FOLDER_MAP, f"Missing key in FOLDER_MAP: {key}"

    def test_reverse_mapping(self, vault: VaultManager):
        """FOLDER_MAP_REVERSE is the inverse of FOLDER_MAP."""
        for k, v in vault.FOLDER_MAP.items():
            assert vault.FOLDER_MAP_REVERSE[v] == k
