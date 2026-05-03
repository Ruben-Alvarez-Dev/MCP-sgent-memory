"""Vault Manager — Obsidian vault with catastrophe-proof writes.

Manages the human-readable vault that complements Qdrant.
All writes are atomic, backed up, and integrity-checked.

Usage:
    from shared.vault_manager import vault

    # Write a note (atomic, backed up)
    vault.write_note("Decisiones", "mi-decision.md", {
        "type": "decision",
        "content": "...",
        "author": "system",
        "tags": ["auth", "jwt"],
    })

    # Process inbox
    vault.process_inbox()

    # Full rebuild from Qdrant
    vault.rebuild()

    # Integrity check
    report = vault.integrity_check()
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Configuration ──────────────────────────────────────────────────

VAULT_PATH = Path(os.path.expanduser(
    os.getenv("VAULT_PATH", str(Path(__file__).resolve().parent.parent.parent / "vault")),
))

SYSTEM_DIR = VAULT_PATH / ".system"
BACKUPS_DIR = SYSTEM_DIR / "backups"
LOCKS_DIR = SYSTEM_DIR / "locks"
TRASH_DIR = SYSTEM_DIR / "trash"
ORPHANED_DIR = SYSTEM_DIR / "orphaned"
MANIFEST_PATH = SYSTEM_DIR / "manifest.json"
CHECKSUMS_PATH = SYSTEM_DIR / "checksums.json"
REPAIR_LOG = SYSTEM_DIR / "repair_log.md"
INTEGRITY_REPORT = SYSTEM_DIR / "integrity_report.md"

LOCK_TIMEOUT = 30  # seconds
MAX_BACKUP_AGE_DAYS = 7
MAX_TRASH_AGE_DAYS = 30
MAX_LOG_AGE_DAYS = 30


# ── Vault Manager ──────────────────────────────────────────────────

class VaultManager:
    """Manages the Obsidian vault with atomic writes and integrity checks."""

    FOLDER_MAP = {
        "Inbox": "inbox", "Decisiones": "decisions", "Conocimiento": "knowledge",
        "Episodios": "episodes", "Entidades": "entities", "Notas": "notes",
        "Personas": "people", "Plantillas": "templates",
    }
    FOLDER_MAP_REVERSE = {v: k for k, v in FOLDER_MAP.items()}

    # Vault naming scheme: L{layer}_{TYPE}_{sequence}.md
    TYPE_CODES = {
        "Inbox": "INBOX", "Decisiones": "DECISION", "Conocimiento": "KNOWLEDGE",
        "Episodios": "EPISODE", "Entidades": "ENTITY", "Notas": "NOTE",
        "Personas": "PERSON", "Plantillas": "TEMPLATE",
    }

    def __init__(self, Lx_persistent_path: Path | None = None):
        self.Lx_persistent_path = Lx_persistent_path or VAULT_PATH
        self._ensure_structure()

    def _ensure_structure(self):
        """Create vault structure if not exists."""
        dirs = [
            self.Lx_persistent_path,
            self.Lx_persistent_path / "Inbox",
            self.Lx_persistent_path / "Decisiones",
            self.Lx_persistent_path / "Conocimiento",
            self.Lx_persistent_path / "Episodios",
            self.Lx_persistent_path / "Entidades",
            self.Lx_persistent_path / "Notas",
            self.Lx_persistent_path / "Personas",
            self.Lx_persistent_path / "Plantillas",
            # EN (system copies)
            self.Lx_persistent_path / "inbox",
            self.Lx_persistent_path / "decisions",
            self.Lx_persistent_path / "knowledge",
            self.Lx_persistent_path / "episodes",
            self.Lx_persistent_path / "entities",
            self.Lx_persistent_path / "notes",
            SYSTEM_DIR,
            BACKUPS_DIR,
            LOCKS_DIR,
            TRASH_DIR / "human-deleted",
            TRASH_DIR / "system-deleted",
            ORPHANED_DIR,
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

    # ── Atomic Write ───────────────────────────────────────────────

    def write_note(
        self,
        folder: str,
        filename: str,
        data: dict[str, Any],
        author: str = "system",
        allow_overwrite_human: bool = False,
    ) -> Path:
        """Atomically write a note with frontmatter.

        Args:
            folder: Vault subfolder (e.g., "Decisiones")
            filename: Note filename (e.g., "mi-decision.md")
            data: {"content": "...", "type": "...", "tags": [...], ...}
            author: "system" or "human"
            allow_overwrite_human: If True, allows overwriting human notes

        Returns:
            Path to the written file.
        """
        dest = self.Lx_persistent_path / folder / filename

        # Check if file is human-authored
        if dest.exists() and not allow_overwrite_human:
            existing = self._read_frontmatter(dest)
            if existing and existing.get("author") == "human":
                # Write as .system-note instead
                note_name = Path(filename).stem
                note_ext = Path(filename).suffix
                dest = self.Lx_persistent_path / folder / f"{note_name}.system-note{note_ext}"

        # Ensure folder exists
        dest.parent.mkdir(parents=True, exist_ok=True)

        # Create lock
        lock_name = filename.replace("/", "_").replace(" ", "_")
        lock_path = LOCKS_DIR / f"{lock_name}.lock"
        self._acquire_lock(lock_path)

        try:
            # Backup existing file
            if dest.exists():
                self._backup_file(dest)

            # Write to temp file
            fd, tmp_path = tempfile.mkstemp(
                dir=str(dest.parent),
                suffix=f".tmp.{os.getpid()}",
            )
            try:
                content = self._render_note(data, author)
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(content)

                # Validate
                if not self._validate_note(tmp_path):
                    os.unlink(tmp_path)
                    raise ValueError(f"Invalid note content: {tmp_path}")

                # Atomic rename
                os.replace(tmp_path, str(dest))

                # Update manifest and checksums
                self._update_manifest(folder, filename, author)
                self._update_checksum(dest)

            except Exception:
                # Clean up temp file on error
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise

        finally:
            self._release_lock(lock_path)

        return dest

    def append_note(
        self,
        folder: str,
        filename: str,
        content: str,
        author: str = "system",
    ) -> Path:
        """Append content to an existing note atomically."""
        dest = self.Lx_persistent_path / folder / filename

        if not dest.exists():
            return self.write_note(folder, filename, {"content": content}, author)

        # Check if human-authored
        frontmatter = self._read_frontmatter(dest)
        if frontmatter and frontmatter.get("author") == "human":
            # Write as .system-note
            note_name = Path(filename).stem
            dest = self.Lx_persistent_path / folder / f"{note_name}.system-note{Path(filename).suffix}"
            return self.write_note(folder, f"{note_name}.system-note{Path(filename).suffix}",
                                   {"content": content}, author)

        # Backup
        self._backup_file(dest)

        # Atomic append
        lock_name = filename.replace("/", "_").replace(" ", "_")
        lock_path = LOCKS_DIR / f"{lock_name}.lock"
        self._acquire_lock(lock_path)

        try:
            fd, tmp_path = tempfile.mkstemp(
                dir=str(dest.parent),
                suffix=f".tmp.{os.getpid()}",
            )
            try:
                existing = dest.read_text(encoding="utf-8")
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(existing)
                    f.write(f"\n\n---\n\n## System Note ({datetime.now(timezone.utc).isoformat()})\n\n")
                    f.write(content)

                os.replace(tmp_path, str(dest))
                self._update_checksum(dest)
            except Exception:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise
        finally:
            self._release_lock(lock_path)

        return dest

    # -- Bilingual Vault Methods --

    def write_note_bilingual(self, folder, filename, data, author="system", en_content=None):
        es_path = self.write_note(folder, filename, data, author)
        en_folder = self.FOLDER_MAP.get(folder, folder.lower())
        en_data = dict(data)
        if en_content:
            en_data["content"] = en_content
        en_path = self.write_note(en_folder, filename, en_data, author)
        return {"es": es_path, "en": en_path}

    def read_note_user(self, folder, filename):
        path = self.Lx_persistent_path / folder / filename
        if path.exists():
            return path.read_text(encoding="utf-8")
        return None

    def read_note_system(self, folder, filename):
        en_folder = self.FOLDER_MAP.get(folder, folder.lower())
        path = self.Lx_persistent_path / en_folder / filename
        if path.exists():
            return path.read_text(encoding="utf-8")
        return None

    def list_notes_bilingual(self, folder):
        es_path = self.Lx_persistent_path / folder
        en_folder = self.FOLDER_MAP.get(folder, folder.lower())
        en_path = self.Lx_persistent_path / en_folder
        es_notes = sorted([f.name for f in es_path.glob("*.md")]) if es_path.exists() else []
        en_notes = sorted([f.name for f in en_path.glob("*.md")]) if en_path.exists() else []
        return {"es": es_notes, "en": en_notes}


    # ── Inbox Processing ───────────────────────────────────────────

    def process_inbox(self) -> list[dict]:
        """Process all notes in Inbox, classify and move to proper folder.

        Returns list of processed items.
        """
        inbox = self.Lx_persistent_path / "Inbox"
        processed = []

        for note_file in sorted(inbox.glob("*.md")):
            try:
                content = note_file.read_text(encoding="utf-8")
                frontmatter = self._read_frontmatter(note_file)
                body = content.split("---", 2)[-1].strip() if "---" in content else content

                # Classify
                classification = self._classify_note(body, frontmatter)

                # Generate frontmatter
                now = datetime.now(timezone.utc).isoformat()
                data = {
                    "type": classification["type"],
                    "layer": classification.get("layer", 0),
                    "created": now,
                    "confidence": classification.get("confidence", 0.5),
                    "source": "inbox-processed",
                    "tags": classification.get("tags", []),
                    "content": body,
                }

                # Extract wikilinks from content
                wikilinks = re.findall(r'\[\[([^\]]+)\]\]', body)
                if wikilinks:
                    data["related"] = wikilinks

                # Move to proper folder
                folder = classification.get("folder", "Conocimiento")
                dest_name = classification.get("filename", note_file.name)

                # Check if destination already exists
                dest = self.Lx_persistent_path / folder / dest_name
                if dest.exists():
                    # Append as system-note
                    self.append_note(folder, dest_name, body, "system")
                else:
                    self.write_note(folder, dest_name, data, "system")

                # Move original to trash
                trash_dest = TRASH_DIR / "system-deleted" / f"{note_file.name}.processed"
                note_file.rename(trash_dest)

                processed.append({
                    "original": note_file.name,
                    "destination": f"{folder}/{dest_name}",
                    "type": classification["type"],
                })

            except Exception as e:
                self._log_repair(f"Failed to process inbox note {note_file.name}: {e}")

        return processed

    def _classify_note(self, body: str, frontmatter: dict | None) -> dict:
        """Classify an inbox note into type and folder."""
        body_lower = body.lower()
        tags = []

        # Decision indicators
        decision_words = ["decisión", "decidimos", "elegimos", "decided", "we chose",
                         "should use", "should not", "must use", "hay que", "vamos a usar"]
        # Episode indicators
        episode_words = ["sesión", "session", "hoy hicimos", "today we", "fix", "fixed",
                        "implementé", "implemented"]
        # Knowledge indicators
        knowledge_words = ["patrón", "pattern", "lección", "lesson", "aprendí", "learned",
                          "ojo", "cuidado", "warning", "gotcha", "tip"]

        decision_score = sum(1 for w in decision_words if w in body_lower)
        episode_score = sum(1 for w in episode_words if w in body_lower)
        knowledge_score = sum(1 for w in knowledge_words if w in body_lower)

        # Extract potential tags from keywords
        tech_keywords = ["auth", "jwt", "qdrant", "embedding", "retrieval", "llm", "docker",
                        "api", "vault", "obsidian", "hybrid", "bm25", "compliance"]
        for kw in tech_keywords:
            if kw in body_lower:
                tags.append(kw)

        if decision_score >= 2:
            return {
                "type": "decision",
                "folder": "Decisiones",
                "layer": 3,
                "confidence": 0.8,
                "tags": tags,
                "filename": self._generate_filename(body, "Decisiones"),
            }
        elif episode_score >= 2:
            return {
                "type": "episode",
                "folder": "Episodios",
                "layer": 2,
                "confidence": 0.7,
                "tags": tags,
                "filename": self._generate_filename(body, "Episodios"),
            }
        elif knowledge_score >= 2:
            return {
                "type": "pattern",
                "folder": "Conocimiento",
                "layer": 4,
                "confidence": 0.75,
                "tags": tags,
                "filename": self._generate_filename(body, "Conocimiento"),
            }
        else:
            # Default: knowledge
            return {
                "type": "note",
                "folder": "Conocimiento",
                "layer": 0,
                "confidence": 0.5,
                "tags": tags,
                "filename": self._generate_filename(body, "Conocimiento"),
            }

    def _generate_filename(self, body: str, folder: str) -> str:
        """Generate a filename from the first line or first few words."""
        first_line = body.strip().split("\n")[0][:80]
        # Sanitize
        name = re.sub(r'[<>:"/\\|?*]', '', first_line)
        name = name.strip().rstrip(".")
        if not name:
            name = f"note-{int(time.time())}"
        # Limit length
        if len(name) > 100:
            name = name[:97] + "..."
        return f"{name}.md"

    # ── Integrity Check ────────────────────────────────────────────

    def integrity_check(self) -> dict:
        """Run full integrity check on the vault.

        Returns report dict.
        """
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "files_expected": 0,
            "files_found": 0,
            "missing": [],
            "orphaned": [],
            "corrupted": [],
            "broken_links": [],
            "repairs": [],
        }

        # Read manifest
        manifest = self._load_manifest()
        checksums = self._load_checksums()

        # Scan actual files
        actual_files = {}
        for folder in ["Inbox", "Decisiones", "Conocimiento", "Episodios",
                       "Entidades", "Notas", "Personas", "Plantillas",
                       "inbox", "decisions", "knowledge", "episodes",
                       "entities", "notes"]:
            folder_path = self.Lx_persistent_path / folder
            if folder_path.exists():
                for f in folder_path.rglob("*.md"):
                    rel = str(f.relative_to(self.Lx_persistent_path))
                    actual_files[rel] = f

        report["files_expected"] = len(manifest)
        report["files_found"] = len(actual_files)

        # Check missing files
        for rel_path in manifest:
            if rel_path not in actual_files:
                report["missing"].append(rel_path)
                # Try to restore from backup
                restored = self._restore_from_backup(rel_path)
                if restored:
                    report["repairs"].append(f"Restored {rel_path} from backup")
                else:
                    report["repairs"].append(f"Cannot restore {rel_path} — no backup")

        # Check orphaned files
        for rel_path in actual_files:
            if rel_path not in manifest:
                report["orphaned"].append(rel_path)
                # Move to orphaned dir
                src = actual_files[rel_path]
                dest = ORPHANED_DIR / src.name
                src.rename(dest)
                report["repairs"].append(f"Moved orphaned {rel_path} to .system/orphaned/")

        # Check corrupted files
        for rel_path, expected_sha in checksums.items():
            actual_file = actual_files.get(rel_path)
            if actual_file and actual_file.exists():
                actual_sha = self._sha256(actual_file)
                if actual_sha != expected_sha:
                    # Check if human-authored
                    frontmatter = self._read_frontmatter(actual_files[rel_path])
                    if frontmatter and frontmatter.get("author") == "human":
                        report["corrupted"].append(f"{rel_path} (human-edited, not restoring)")
                    else:
                        # Restore from backup
                        restored = self._restore_from_backup(rel_path)
                        if restored:
                            report["repairs"].append(f"Restored corrupted {rel_path} from backup")

        # Check broken wikilinks
        for rel_path, file_path in actual_files.items():
            try:
                content = file_path.read_text(encoding="utf-8")
                links = re.findall(r'\[\[([^\]]+)\]\]', content)
                for link in links:
                    # Check if target exists
                    target = self.Lx_persistent_path / f"{link}.md"
                    if not target.exists():
                        report["broken_links"].append({
                            "source": rel_path,
                            "target": link,
                        })
            except Exception:
                pass

        # Write report
        self._write_integrity_report(report)

        return report

    # ── Rebuild from Qdrant ────────────────────────────────────────

    def rebuild(self, qdrant_url: str = "http://127.0.0.1:6333") -> dict:
        """Rebuild entire vault from Qdrant data.

        This is the catastrophe recovery protocol.
        """
        import httpx

        result = {
            "files_rebuilt": 0,
            "errors": [],
        }

        # Move current vault to trash
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        trash_backup = TRASH_DIR / f"pre-rebuild-{timestamp}"
        if self.Lx_persistent_path.exists():
            trash_backup.mkdir(parents=True, exist_ok=True)
            for item in self.Lx_persistent_path.iterdir():
                if item.name == ".system":
                    continue
                item.rename(trash_backup / item.name)

        # Rebuild structure
        self._ensure_structure()

        # Fetch all points from Qdrant
        collections = ["L0_L4_memory", "L2_conversations", "L3_facts"]

        for collection in collections:
            try:
                with httpx.Client() as client:
                    resp = client.post(
                        f"{qdrant_url}/collections/{collection}/points/scroll",
                        json={"limit": 10000, "with_payload": True},
                    )
                    if resp.status_code != 200:
                        result["errors"].append(f"Failed to scroll {collection}: {resp.status_code}")
                        continue

                    points = resp.json().get("result", {}).get("points", [])
                    for point in points:
                        payload = point.get("payload", {})
                        content = payload.get("content", "")
                        if not content:
                            continue

                        layer = payload.get("layer", 0)
                        mem_type = payload.get("type", "")
                        created = payload.get("created_at", "")

                        # Determine folder
                        folder = self._layer_to_folder(layer, mem_type)

                        # Generate filename
                        filename = f"{mem_type}_{point['id']}.md"

                        # Extract wikilinks
                        wikilinks = re.findall(r'\[\[([^\]]+)\]\]', content)

                        data = {
                            "type": mem_type,
                            "layer": layer,
                            "created": created or datetime.now(timezone.utc).isoformat(),
                            "confidence": payload.get("confidence", 0.5),
                            "source": "qdrant-rebuild",
                            "tags": payload.get("tags", []),
                            "content": content,
                        }
                        if wikilinks:
                            data["related"] = wikilinks

                        try:
                            self.write_note(folder, filename, data, "system")
                            result["files_rebuilt"] += 1
                        except Exception as e:
                            result["errors"].append(f"Failed to write {folder}/{filename}: {e}")

            except Exception as e:
                result["errors"].append(f"Failed to fetch {collection}: {e}")

        # Run integrity check
        self.integrity_check()

        return result

    def _layer_to_folder(self, layer: int, mem_type: str) -> str:
        """Map memory layer/type to vault folder."""
        if mem_type == "decision":
            return "Decisiones"
        elif layer == 0:
            return "Inbox"
        elif layer == 2:
            return "Episodios"
        elif layer == 3:
            return "Decisiones"
        elif layer == 4:
            return "Conocimiento"
        elif layer == 5:
            return "Conocimiento"
        else:
            return "Conocimiento"

    # ── Internal Helpers ───────────────────────────────────────────


    def _next_id(self, layer: str) -> int:
        import json as _json
        counter_path = self.Lx_persistent_path / ".system" / "counter.json"
        if counter_path.exists():
            counters = _json.loads(counter_path.read_text())
        else:
            counters = {"next": {}}
        key = "Lx" if layer == "Lx" else "L" + str(layer)
        current = counters.get("next", {}).get(key, 1)
        counters.setdefault("next", {})[key] = current + 1
        counter_path.parent.mkdir(parents=True, exist_ok=True)
        counter_path.write_text(_json.dumps(counters, indent=2))
        return current

    def _generate_vault_filename(self, folder: str) -> str:
        layer_map = {
            "Inbox": "L0", "Decisiones": "L3", "Conocimiento": "L3",
            "Episodios": "L2", "Entidades": "L3", "Notas": "Lx",
            "Personas": "Lx", "Plantillas": "Lx",
            "inbox": "L0", "decisions": "L3", "knowledge": "L3",
            "episodes": "L2", "entities": "L3", "notes": "Lx",
            "people": "Lx", "templates": "Lx",
        }
        layer = layer_map.get(folder, "Lx")
        type_code = self.TYPE_CODES.get(folder, "NOTE")
        seq = self._next_id(layer)
        return "{}_{:04d}.md".format(layer + "_" + type_code, seq)

    def _render_note(self, data: dict, author: str) -> str:
        """Render a note with YAML frontmatter."""
        content = data.pop("content", "")

        # Build frontmatter
        fm_lines = ["---"]
        fm_lines.append(f"author: {author}")
        fm_lines.append(f"created: {datetime.now(timezone.utc).isoformat()}")

        for key, value in data.items():
            if isinstance(value, list):
                fm_lines.append(f"{key}: [{', '.join(str(v) for v in value)}]")
            elif isinstance(value, bool):
                fm_lines.append(f"{key}: {'true' if value else 'false'}")
            else:
                fm_lines.append(f"{key}: {value}")

        fm_lines.append("---")

        return "\n".join(fm_lines) + "\n\n" + content

    def _validate_note(self, path: str) -> bool:
        """Validate note content."""
        try:
            content = Path(path).read_text(encoding="utf-8")
            # Check UTF-8 validity
            content.encode("utf-8")
            # Check size
            if len(content) > 10 * 1024 * 1024:  # 10MB
                return False
            # Check frontmatter exists
            if not content.startswith("---"):
                return False
            parts = content.split("---", 2)
            if len(parts) < 3:
                return False
            return True
        except Exception:
            return False

    def _read_frontmatter(self, path: Path) -> dict | None:
        """Read YAML frontmatter from a note."""
        try:
            content = path.read_text(encoding="utf-8")
            if not content.startswith("---"):
                return None
            parts = content.split("---", 2)
            if len(parts) < 3:
                return None
            import yaml
            return yaml.safe_load(parts[1])
        except Exception:
            return None

    def _acquire_lock(self, lock_path: Path):
        """Acquire a lock file with timeout."""
        start = time.monotonic()
        while True:
            if lock_path.exists():
                try:
                    lock_data = json.loads(lock_path.read_text())
                    age = time.time() - lock_data.get("timestamp", 0)
                    if age > LOCK_TIMEOUT:
                        # Stale lock
                        lock_path.unlink()
                        break
                except Exception:
                    lock_path.unlink()
                    break

                if time.monotonic() - start > LOCK_TIMEOUT:
                    raise TimeoutError(f"Could not acquire lock: {lock_path}")
                time.sleep(0.1)
            else:
                lock_path.write_text(json.dumps({
                    "pid": os.getpid(),
                    "timestamp": time.time(),
                }))
                break

    def _release_lock(self, lock_path: Path):
        """Release a lock file."""
        if lock_path.exists():
            lock_path.unlink()

    def _backup_file(self, path: Path):
        """Backup a file before modification."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_dir = BACKUPS_DIR / timestamp
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(path), str(backup_dir / path.name))

    def _restore_from_backup(self, rel_path: str) -> bool:
        """Restore a file from the latest backup."""
        file_name = Path(rel_path).name
        # Find latest backup
        if not BACKUPS_DIR.exists():
            return False

        backups = sorted(BACKUPS_DIR.iterdir(), reverse=True)
        for backup_dir in backups:
            backup_file = backup_dir / file_name
            if backup_file.exists():
                dest = self.Lx_persistent_path / rel_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(backup_file), str(dest))
                self._update_checksum(dest)
                return True

        return False

    def _update_manifest(self, folder: str, filename: str, author: str):
        """Update the manifest with a file entry."""
        manifest = self._load_manifest()
        rel_path = f"{folder}/{filename}"
        manifest[rel_path] = {
            "folder": folder,
            "filename": filename,
            "author": author,
            "last_modified": datetime.now(timezone.utc).isoformat(),
        }
        self._save_manifest(manifest)

    def _update_checksum(self, path: Path):
        """Update checksum for a file."""
        if not path.exists():
            return
        checksums = self._load_checksums()
        rel_path = str(path.relative_to(self.Lx_persistent_path))
        checksums[rel_path] = self._sha256(path)
        self._save_checksums(checksums)

    def _load_manifest(self) -> dict:
        if MANIFEST_PATH.exists():
            return json.loads(MANIFEST_PATH.read_text())
        return {}

    def _save_manifest(self, manifest: dict):
        MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))

    def _load_checksums(self) -> dict:
        if CHECKSUMS_PATH.exists():
            return json.loads(CHECKSUMS_PATH.read_text())
        return {}

    def _save_checksums(self, checksums: dict):
        CHECKSUMS_PATH.write_text(json.dumps(checksums, indent=2))

    def _sha256(self, path: Path) -> str:
        h = hashlib.sha256()
        h.update(path.read_bytes())
        return h.hexdigest()

    def _log_repair(self, message: str):
        """Append to repair log."""
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        line = f"- [{timestamp}] {message}"
        if REPAIR_LOG.exists():
            content = REPAIR_LOG.read_text()
            REPAIR_LOG.write_text(content + "\n" + line)
        else:
            REPAIR_LOG.write_text(f"# Repair Log\n\n{line}")

    def _write_integrity_report(self, report: dict):
        """Write integrity report to file."""
        lines = [f"# Integrity Report — {report['timestamp']}\n"]
        lines.append(f"- Files expected: {report['files_expected']}")
        lines.append(f"- Files found: {report['files_found']}")
        lines.append(f"- Missing: {len(report['missing'])}")
        lines.append(f"- Orphaned: {len(report['orphaned'])}")
        lines.append(f"- Corrupted: {len(report['corrupted'])}")
        lines.append(f"- Broken links: {len(report['broken_links'])}")
        lines.append(f"- Repairs: {len(report['repairs'])}")

        if report["missing"]:
            lines.append("\n## Missing Files\n")
            for f in report["missing"]:
                lines.append(f"- {f}")

        if report["broken_links"]:
            lines.append("\n## Broken Wikilinks\n")
            for link in report["broken_links"]:
                lines.append(f"- {link['source']} → [[{link['target']}]]")

        if report["repairs"]:
            lines.append("\n## Repairs\n")
            for r in report["repairs"]:
                lines.append(f"- {r}")

        INTEGRITY_REPORT.write_text("\n".join(lines))


# ── Singleton ──────────────────────────────────────────────────────

vault = VaultManager()
