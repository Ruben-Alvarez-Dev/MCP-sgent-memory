"""KB pipeline — conocimiento del agente → vault de Obsidian del usuario.

obsidian-kb-pipeline v3 (openspec/changes/obsidian-kb-pipeline).

Flujo autónomo SIN intervención humana:
    L3 fact (importance ≥ umbral, superviviente ≥ min_age)
      → captura en <vault>/<inbox>/         (estado: captura)
      → borrador en <vault>/<wiki>/         (estado: borrador-agente)
      → [editor agéntico: pi -p]            (estado: pulido-agente)

Garantías:
- Escrituras SOLO en las dos rutas del flujo Para del usuario (jail).
- Índice idempotente (.memory-index.json) + reconcile() que sobrevive a
  moves humanos (el frontmatter `source:` persiste al mover).
- Escritura atómica (tmp+rename). Los ficheros del usuario jamás se tocan.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import unicodedata
from datetime import UTC, datetime
from pathlib import Path


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def slugify(text: str, max_words: int = 7) -> str:
    """Slug ASCII estable: minúsculas, sin acentos, guiones."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    words = re.findall(r"[a-z0-9]+", text.lower())
    return "-".join(words[:max_words]) or "nota"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


class KBEngine:
    """Refinería de conocimiento: SQLite del agente → vault de Obsidian."""

    def __init__(self, db=None):
        self._db = db
        vault = _env("MEMORY_OBSIDIAN_VAULT")
        self.vault = Path(os.path.expanduser(vault)) if vault else None
        self.inbox = _env("MEMORY_KB_INBOX", "00 Inbox")
        self.wiki = _env("MEMORY_KB_WIKI", "20 Wiki/Borradores-agente")
        self.importance_threshold = float(_env("MEMORY_KB_IMPORTANCE", "0.8"))
        self.min_age_days = float(_env("MEMORY_KB_MIN_AGE_DAYS", "1"))
        self.max_per_run = int(_env("MEMORY_KB_MAX_PER_RUN", "10"))
        self.enabled = self.vault is not None

    # ── rutas (con jail) ──────────────────────────────────────────────

    def _allowed(self) -> list[Path]:
        if not self.enabled:
            return []
        return [self.vault / self.inbox, self.vault / self.wiki]

    def _jail(self, path: Path) -> Path:
        """KB-08: la ruta final DEBE vivir bajo Inbox/ o Wiki/ del vault."""
        resolved = path.resolve()
        for allowed in self._allowed():
            try:
                resolved.relative_to(allowed.resolve())
                return resolved
            except ValueError:
                continue
        raise PermissionError(f"ruta fuera del flujo KB (jail): {path}")

    def _inbox_dir(self) -> Path:
        return self._jail(self.vault / self.inbox)

    def _wiki_dir(self) -> Path:
        return self._jail(self.vault / self.wiki)

    # ── índice de trazabilidad (idempotente) ──────────────────────────

    @property
    def _index_path(self) -> Path:
        return self._inbox_dir() / ".memory-index.json"

    def _load_index(self) -> dict:
        try:
            return json.loads(self._index_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_index(self, index: dict) -> None:
        _atomic_write(self._index_path, json.dumps(index, indent=1, ensure_ascii=False))

    def _index_set(self, memory_id: str, path: Path, estado: str, sha: str) -> None:
        idx = self._load_index()
        entry = {"path": str(path), "estado": estado, "sha256": sha}
        existing = idx.get(memory_id)
        if existing is None:
            idx[memory_id] = entry
        elif isinstance(existing, list):
            # una memoria puede tener varias notas (captura + borrador de wiki)
            if entry not in existing:
                existing.append(entry)
            idx[memory_id] = existing
        else:
            idx[memory_id] = [existing, entry] if existing != entry else [existing]
        self._save_index(idx)

    # ── KB-03: captura en el inbox del usuario ────────────────────────

    def capture_to_inbox(self, memory_id: str, content: str, meta: dict) -> Path:
        if not self.enabled:
            raise RuntimeError("MEMORY_OBSIDIAN_VAULT no configurado")
        importance = float(meta.get("importance", 0.5))
        mem_type = str(meta.get("mem_type", "fact") or "fact")
        agent = str(meta.get("agent", "mcp"))
        title = content.strip().split(".")[0][:60]
        slug = f"{mem_type}-{slugify(title)}"
        front = (
            f"---\ntipo: captura\nsource: memory:{memory_id}\nagent: {agent}\n"
            f"created: {datetime.now(UTC).date().isoformat()}\n"
            f"importance: {importance}\nestado: captura\n"
            f"tags: [memoria, origin/agent, {mem_type}]\n---\n\n"
        )
        path = self._jail(self._inbox_dir() / f"{slug}.md")
        _atomic_write(path, front + content.strip() + "\n")
        sha = hashlib.sha256((front + content).encode()).hexdigest()
        self._index_set(memory_id, path, "captura", sha)
        return path

    # ── candidatos a promoción (importancia + supervivencia) ──────────

    def candidates(self) -> list[dict]:
        if self._db is None:
            return []
        conn = self._db._conn
        rows = conn.execute(
            "SELECT id, payload, created_at FROM points WHERE collection=?",
            (self._db.collection,),
        ).fetchall()
        index = self._load_index()
        now = time.time()
        out = []
        for r in rows:
            mid = r["id"]
            if mid in index:
                continue  # ya capturado (idempotencia)
            try:
                payload = json.loads(r["payload"])
            except json.JSONDecodeError:
                continue
            content = str(payload.get("content", "")).strip()
            importance = float(payload.get("importance", 0) or 0)
            created = payload.get("created_at") or r["created_at"]
            try:
                age_days = (now - datetime.fromisoformat(str(created)).timestamp()) / 86400
            except (ValueError, TypeError):
                age_days = self.min_age_days  # fecha desconocida: no bloquear
            if not content or len(content) < 20:
                continue
            out.append({"memory_id": mid, "content": content, "importance": importance,
                        "age_days": age_days,
                        "mem_type": str(payload.get("mem_type", "fact")),
                        "agent": str(payload.get("agent", "mcp")),
                        "agent_scope": str(payload.get("agent_scope", "shared"))})
        out.sort(key=lambda c: -c["importance"])
        return out

    # ── KB-04: borrador de wiki (plantilla del usuario) ───────────────

    def write_wiki_draft(self, cand: dict) -> Path:
        title = cand["content"].strip().split(".")[0][:60]
        slug = slugify(title)
        is_fix = cand["mem_type"] in ("bug_fix", "config")
        body = (
            f"---\ntipo: wiki\nestado: borrador-agente\n"
            f"source: memory:{cand['memory_id']}\nverificado: false\n"
            f"created: {datetime.now(UTC).date().isoformat()}\n"
            f"tags: [wiki, memoria]\n---\n\n"
            f"# {title}\n\n"
            f"## Concepto en 3 líneas\n\n{cand['content'].strip()}\n\n"
            + ("" if not is_fix else
               "## Gotchas y cosas que la doc no cuenta\n\n"
               f"{cand['content'].strip()}\n\n")
            + "## Relacionadas\n\n(pendiente de destilado por el editor)\n"
        )
        path = self._jail(self._wiki_dir() / f"{slug}.md")
        _atomic_write(path, body)
        sha = hashlib.sha256(body.encode()).hexdigest()
        self._index_set(cand["memory_id"], path, "borrador-agente", sha)
        return path

    # ── pasada de promoción (idempotente) ─────────────────────────────

    def promote_pending(self) -> dict:
        """Captura candidatos nuevos y promueve los que superan umbrales."""
        if not self.enabled:
            return {"enabled": False}
        out = {"captured": [], "promoted": [], "skipped": 0}
        for cand in self.candidates()[: self.max_per_run]:
            if cand["importance"] < self.importance_threshold:
                out["skipped"] += 1
                continue
            try:
                path = self.capture_to_inbox(cand["memory_id"], cand["content"],
                                             {"importance": cand["importance"],
                                              "mem_type": cand["mem_type"],
                                              "agent": cand["agent"]})
                out["captured"].append(str(path))
            except PermissionError as e:
                out["skipped"] += 1
                out.setdefault("errors", []).append(f"jail: {e}")
                continue
            if (cand["importance"] >= self.importance_threshold
                    and cand["age_days"] >= self.min_age_days):
                wpath = self.write_wiki_draft(cand)
                out["promoted"].append(str(wpath))
        return out

    # ── reconcile: sobrevive a moves humanos ──────────────────────────

    def reconcile(self) -> dict:
        """Re-escanea Inbox/Wiki buscando `source: memory:<id>` y actualiza
        el índice (el frontmatter sobrevive a moves/renombres humanos)."""
        if not self.enabled:
            return {"enabled": False}
        src_re = re.compile(r"^source: memory:(\S+)", re.MULTILINE)
        est_re = re.compile(r"^estado: (\S+)", re.MULTILINE)
        found: dict[str, list[dict]] = {}
        for md in self.vault.rglob("*.md"):
            if ".obsidian" in md.parts:
                continue
            head = md.read_text(encoding="utf-8", errors="ignore")[:600]
            m = src_re.search(head)
            if m:
                est = est_re.search(head)
                found.setdefault(m.group(1), []).append(
                    {"path": str(md), "estado": est.group(1) if est else "?"})
        idx = self._load_index()
        for mid, entries in found.items():
            prev = idx.get(mid)
            prev_list = prev if isinstance(prev, list) else ([prev] if prev else [])
            for entry in entries:
                if entry not in prev_list:
                    prev_list.append(entry)
            idx[mid] = prev_list
        self._save_index(idx)
        return {"reconciled": len(found), "index_size": len(idx)}

    # ── KB-05: integridad con alcance al agente ───────────────────────

    def integrity_check(self) -> dict:
        if not self.enabled:
            return {"enabled": False}
        problems = []
        idx = self._load_index()
        entries = [e for v in idx.values() for e in (v if isinstance(v, list) else [v])]
        for e in entries:
            p = Path(e["path"])
            if not p.exists():
                problems.append(f"{e.get('source', e.get('path'))}: nota desaparecida ({p})")
        rep = self.verify_fts() if self._db else {"passed": True}
        return {"enabled": True, "notes": len(entries), "fts": rep,
                "problems": problems, "passed": not problems and rep.get("passed", True)}

    def verify_fts(self) -> dict:
        conn = self._db._conn
        missing = conn.execute(
            "SELECT COUNT(*) FROM points p WHERE NOT EXISTS "
            "(SELECT 1 FROM points_fts t WHERE t.rowid=p.rowid)").fetchone()[0]
        orphans = conn.execute(
            "SELECT COUNT(*) FROM points_fts t WHERE NOT EXISTS "
            "(SELECT 1 FROM points p WHERE p.rowid=t.rowid)").fetchone()[0]
        return {"passed": missing == 0 and orphans == 0,
                "fts_missing": missing, "fts_orphans": orphans}
