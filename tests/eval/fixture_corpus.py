"""Deterministic fixture corpus for eval-40 (M3-retrieval, task 4).

Builds a throwaway memory.db whose points are REAL chunks of this repo
(sanitize.py, embedding.py, L0_capture, retrieval, conversation_db, scope,
README, ...) plus synthetic-but-traceable decision records and conversation
summaries derived from openspec/changes/*.

Properties:
- Deterministic: same working tree -> identical manifest (ids, contents,
  sources). Chunk extraction is marker-based (`_between`), never line-based.
- Idempotent: DROPs the `points` table before rebuilding (never appends).
- Honest: ids eval-1..eval-38, layers 1-4, agent_scope='shared' everywhere.
  Queries that name dead symbols (AuthService, build_repo_index_points) are
  judged against the closest REAL analogue; the mismatch is a system finding
  the eval must surface, not something the fixture hides.

Used by scripts/run_eval.py and tests/eval/test_fixture_determinista.py.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from shared.retrieval import bm25_tokenize
from shared.memory_db import MemoryDB

REPO_ROOT = Path(__file__).resolve().parents[2]
COLLECTION = "L0_L4_memory"
DIM = 1024

_MIN_CHARS, MAX_CHARS = 180, 620


def _src(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def _between(text: str, start: str, end: str | None = None, cap: int = MAX_CHARS) -> str:
    """Marker-based chunk extraction. Raises (loudly) if a marker disappears."""
    i = text.index(start)
    j = text.index(end, i + len(start)) if end else len(text)
    chunk = text[i:j].strip()
    if len(chunk) > cap:
        chunk = chunk[:cap].rstrip() + " …"
    if len(chunk) < _MIN_CHARS:
        raise ValueError(f"chunk too short ({len(chunk)} chars): {start[:48]!r}")
    return chunk


# ── Real-code chunks (layer 1) ────────────────────────────────────

def _code_docs() -> list[dict]:
    sanitize = _src("src/shared/sanitize.py")
    l0_main = _src("src/L0_capture/server/main.py")
    retr = _src("src/shared/retrieval/__init__.py")
    repo_map = _src("src/shared/retrieval/repo_map.py")
    conv_db = _src("src/shared/conversation_db.py")
    scope = _src("src/shared/scope.py")
    memory_db = _src("src/shared/memory_db.py")
    l0_l4 = _src("src/L0_to_L4_consolidation/server/main.py")
    l5 = _src("src/L5_routing/server/main.py")
    readme = _src("README.md")
    api = _src("src/shared/api_server.py")

    def doc(content: str, source: str, symbols: list[str], layer: int, dtype: str) -> dict:
        return {
            "content": content,
            "source_file": source,
            "symbols": symbols,
            "layer": layer,
            "type": dtype,
        }

    return [
        # -- sanitize.py --
        doc(
            _between(sanitize, "Principles:", "Usage in any server:"),
            "src/shared/sanitize.py",
            ["sanitize_text", "SanitizeError", "sanitize"],
            1,
            "code",
        ),
        doc(
            _between(sanitize, "def sanitize_user_id", "def sanitize_thread_id"),
            "src/shared/sanitize.py",
            ["sanitize_user_id", "auth", "user_id"],
            1,
            "code",
        ),
        doc(
            _between(sanitize, "def validate_memorize", "def validate_add_memory"),
            "src/shared/sanitize.py",
            ["validate_memorize", "validate_save_decision", "validate_ingest_event"],
            1,
            "code",
        ),
        # -- embedding.py --
        # -- L0_capture --
        doc(
            _between(l0_main, "async def heartbeat", "    status = HeartbeatStatus"),
            "src/L0_capture/server/main.py",
            ["heartbeat", "HeartbeatResult", "prefetch_queries"],
            1,
            "code",
        ),
        doc(
            _between(l0_main, "async def memorize", "@mcp.tool", cap=MAX_CHARS),
            "src/L0_capture/server/main.py",
            ["memorize", "ingest_event", "MemoryItem"],
            1,
            "code",
        ),
        # -- retrieval --
        doc(
            _between(retr, '"""Retrieval Router', "import asyncio"),
            "src/shared/retrieval/__init__.py",
            ["retrieve", "classify_intent", "RetrievalProfile"],
            1,
            "code",
        ),
        doc(
            _between(retr, "# v1.4: freshness joins", "all_items.sort"),
            "src/shared/retrieval/__init__.py",
            ["combined_score", "_rank_and_fuse", "ranking"],
            1,
            "code",
        ),
        doc(
            _between(retr, "async def _retrieve_hybrid", "    if not query_text:"),
            "src/shared/retrieval/__init__.py",
            ["_retrieve_hybrid", "hybrid search", "agent_scope filter"],
            1,
            "code",
        ),
        doc(
            _between(repo_map, "def build_repo_map", '    if target.suffix == ".py":'),
            "src/shared/retrieval/repo_map.py",
            ["build_repo_map", "RepoMap", "repo map"],
            1,
            "code",
        ),
        # -- conversation_db.py --
        doc(
            _between(conv_db, '"""SQLite + FTS5 storage', "from __future__"),
            "src/shared/conversation_db.py",
            ["messages_fts", "FTS5", "threads"],
            1,
            "code",
        ),
        doc(
            _between(conv_db, "def _fts_escape", "def search_fts"),
            "src/shared/conversation_db.py",
            ["search_fts", "_fts_escape", "FTS5 MATCH"],
            1,
            "code",
        ),
        doc(
            _between(conv_db, "def save_thread", "    now = datetime.now"),
            "src/shared/conversation_db.py",
            ["save_thread", "get_thread", "conversation thread"],
            1,
            "code",
        ),
        # -- scope.py --
        doc(
            _between(scope, '"""Canonical tenant scope handling', "from __future__"),
            "src/shared/scope.py",
            ["normalize_scope", "ScopeError", "scope"],
            1,
            "code",
        ),
        doc(
            _between(scope, "def scope_jail_path", "def scope_dir_hashed"),
            "src/shared/scope.py",
            ["scope_jail_path", "assert_contained", "isolation"],
            1,
            "code",
        ),
        # -- memory_db.py --
        doc(
            _between(memory_db, "def _search_fts_sync", "async def search_fts"),
            "src/shared/memory_db.py",
            ["search_fts", "FTS5", "two-phase"],
            1,
            "code",
        ),
        doc(
            _between(memory_db, "    def _delete_one", "    def _update_payload_one"),
            "src/shared/memory_db.py",
            ["delete", "_delete_one", "TOCTOU"],
            1,
            "code",
        ),
        # -- consolidation / routing --
        doc(
            _between(l0_l4, '"""L0_to_L4_consolidation', "from __future__"),
            "src/L0_to_L4_consolidation/server/main.py",
            ["L0_to_L4_consolidation", "consolidation", "dream"],
            1,
            "code",
        ),
        doc(
            _between(l5, "async def check_reminders", "# M2: engine-level scope filter"),
            "src/L5_routing/server/main.py",
            ["check_reminders", "push_reminder", "pending reminders"],
            1,
            "code",
        ),
        # -- reference docs (layer 3) --
        doc(
            _between(readme, "> **Persistent multi-layer memory", "## How It Works"),
            "README.md",
            ["backpack", "MCP tools", "architecture"],
            3,
            "doc",
        ),
        doc(
            _between(api, '"""\nBackpack HTTP API', "from __future__"),
            "src/shared/api_server.py",
            ["api_server", "sidecar", "8890"],
            3,
            "doc",
        ),
    ]


# ── Synthetic conversation summaries (layer 2) ────────────────────
# Traceable to real topics: openspec/changes/*, docs/archive/*, module docstrings.

def _conversation_docs() -> list[dict]:
    return [
        {
            "content": (
                "Resumen de conversación — vault: hablamos del vault bilingüe de Obsidian. "
                "El contenido de las notas .md queda en el idioma de origen (es/en) y los tags "
                "van en inglés canónico; vault_manager aplica sanitize_filename antes de "
                "escribir, lo que evitó el problema de rutas con acentos que discutimos. "
                "Pendiente: sincronizar el vault con data/memory."
            ),
            "source_file": "synthetic:conv/vault-es.md",
            "symbols": ["vault", "bilingual", "Obsidian"],
            "layer": 2,
            "type": "conversation_summary",
        },
        {
            "content": (
                "Resumen de conversación — hooks: lo que hablamos de los hooks de OpenCode. "
                "El plugin dispara fetch() contra el sidecar HTTP en 127.0.0.1:8890 en cada "
                "prompt, tool call y edición de fichero, y el sidecar ejecuta la operación de "
                "memoria sin pasar por el LLM. Conclusión: si el hook no dispara la "
                "consolidación, revisar el log del sidecar y el turn_count del heartbeat "
                "(promotion_due depende de PROMOTION_INTERVAL)."
            ),
            "source_file": "synthetic:conv/hooks-es.md",
            "symbols": ["hooks", "OpenCode", "sidecar"],
            "layer": 2,
            "type": "conversation_summary",
        },
        {
            "content": (
                "Resumen de conversación — reminders: mencionamos el problema de los "
                "reminders de contexto. Los guarda L5_routing como JSON bajo data/L5-selective "
                "con scope por agente; el problema era que check_reminders devolvía duplicados "
                "tras la migración legacy y que push_reminder fallaba si el embedding server "
                "no respondía. Solución acordada: degradar a hash_vector determinista (RET-06) "
                "y sanitizar reminder_id con regex estricto."
            ),
            "source_file": "synthetic:conv/reminders-es.md",
            "symbols": ["reminders", "check_reminders", "push_reminder"],
            "layer": 2,
            "type": "conversation_summary",
        },
        {
            "content": (
                "Conversation summary — sampling support: what we said about sampling in "
                "llama.cpp. The server exposes sampling params (temperature, top_p, top_k) on "
                "its completion endpoint, but the memory system only consumes the embedding "
                "endpoint; sampling only matters for the consolidation LLM. We agreed to keep "
                "default sampling for background summarization and not to expose sampling "
                "knobs through MCP tools."
            ),
            "source_file": "synthetic:conv/sampling-en.md",
            "symbols": ["sampling", "llama.cpp", "temperature"],
            "layer": 2,
            "type": "conversation_summary",
        },
        {
            "content": (
                "Conversation summary — sqlite-vec: we discussed sqlite-vec earlier as the "
                "vector index for memory.db. Decision recap: stdlib-only brute-force cosine "
                "for now, no sqlite-vec and no numpy, because the real points table is nearly "
                "empty; the documented trigger to revisit is >50k points, at which point "
                "health() will report scan_ms."
            ),
            "source_file": "synthetic:conv/sqlite-vec-en.md",
            "symbols": ["sqlite-vec", "memory.db", "scan_ms"],
            "layer": 2,
            "type": "conversation_summary",
        },
        {
            "content": (
                "Conversation summary — isolation leaks: what did we cover about isolation "
                "leaks in the M1 audit. Per-scope collection names allowed injection and "
                "sibling-scope reads; the fix was canonical scopes (normalize_scope raising "
                "ScopeError) plus engine-level SQL WHERE filters with bound parameters "
                "(ISO-05). The adversarial spy test now re-runs on every storage change."
            ),
            "source_file": "synthetic:conv/isolation-leaks-en.md",
            "symbols": ["isolation", "leaks", "normalize_scope"],
            "layer": 2,
            "type": "conversation_summary",
        },
    ]


# ── Synthetic decision records (layer 4) ──────────────────────────
# Each one summarizes a REAL openspec/changes decision; provenance in based_on.

def _decision_docs() -> list[dict]:
    def dec(content: str, slug: str, symbols: list[str], based_on: str) -> dict:
        return {
            "content": content,
            "source_file": f"synthetic:decisions/{slug}.md",
            "symbols": symbols,
            "layer": 4,
            "type": "decision",
            "based_on": based_on,
        }

    return [
        dec(
            "Decisión (M2-storage): SQLite memory.db en vez de Qdrant. Demolimos el daemon "
            "Qdrant (puerto 6333, colección L0_L4_memory) y unificamos memoria densa, "
            "conversaciones y facts en un solo archivo SQLite con stdlib. Motivos: un proceso "
            "menos que caer ('qdrant connection refused'), sin puerto HTTP local sin "
            "autenticación (cualquier proceso podía leer /points/scroll en el 6333), backups "
            "triviales y aislamiento enforceable en SQL. La configuración legacy de Qdrant "
            "(QDRANT_URL=http://127.0.0.1:6333 en config/mcp.json) ya no se usa; MemoryDB "
            "mantiene paridad de interfaz con QdrantClient para que la migración de los "
            "servidores MCP fuera solo cambiar constructor.",
            "sqlite-vs-qdrant",
            ["Qdrant", "SQLite", "memory.db", "6333"],
            "openspec/changes/M2-storage/design.md",
        ),
        dec(
            "Decisión: modelo de embeddings BGE-M3 (1024 dims) en vez de MiniLM. Elegimos "
            "BGE-M3 cuantizado (bge-m3-Q4_K_M.gguf, 417MB) servido por llama-server en el "
            "puerto 8081: 1024 dimensiones separan mejor relevantes de irrelevantes que los "
            "384 de MiniLM en nuestros benchmarks (0.72 vs 0.56 de cosine en pares "
            "relevantes) y su soporte multilingüe es/en es clave para el vault bilingüe. La "
            "abstracción EMBEDDING_BACKEND (llama_cpp | http | noop) permite cambiar de "
            "modelo sin tocar código; EMBEDDING_ENDPOINT apunta al servidor "
            "OpenAI-compatible.",
            "bge-m3-vs-minilm",
            ["BGE-M3", "MiniLM", "embeddings", "1024"],
            "docs/archive/dev/04-BENCHMARKS.md",
        ),
        dec(
            "Decisión: el vault es bilingüe (es/en). El usuario trabaja en español pero los "
            "agentes y el código operan en inglés; decidimos contenido libre en el idioma de "
            "origen, tags y frontmatter en inglés canónico y títulos de archivo en inglés "
            "tras sanitize_filename. La búsqueda híbrida (FTS5 + BGE-M3 multilingüe) tolera "
            "el mixed-language. Alternativa descartada: traducir todo al inglés, perdía "
            "matices de las notas del usuario.",
            "vault-bilingue",
            ["vault", "bilingüe", "es/en"],
            "src/shared/vault_manager/__init__.py",
        ),
        dec(
            "Decisión (M3, RET-04): eliminar el micro-LLM del ranking. Jubilamos "
            "rank_by_relevance y el micro-LLM del path de retrieval: añadía latencia, otro "
            "modelo que mantener y ganancia nula sobre el ranking determinista. El ranking "
            "queda combined_score = level_weight*score*0.5 + recency*0.2 + freshness*0.3 con "
            "fusión dense+sparse (RET-05). get_small_llm sobrevive solo para compliance con "
            "degradación graceful.",
            "micro-llm-retirement",
            ["micro-LLM", "ranking", "RET-04"],
            "openspec/changes/M3-retrieval/design.md",
        ),
        dec(
            "Decision (M1-lite/M2, ISO-05): scope isolation is engine-level. Every read "
            "requires an explicit filter — search/scroll fail closed with ScopeRequiredError "
            "otherwise — and scope matching happens inside the SQL WHERE clause with bound "
            "parameters, never in Python post-filtering. normalize_scope canonicalizes "
            "tenant segments (ScopeError on traversal/glob/reserved input) and match.any "
            "merges own+shared via a single IN clause: sibling scopes are unreachable by "
            "construction, not by convention.",
            "scope-isolation",
            ["scope isolation", "ISO-05", "ScopeRequiredError"],
            "openspec/changes/M2-storage/design.md",
        ),
        dec(
            "Decision: HTTP sidecar on port 8890. The Backpack API sidecar "
            "(shared/api_server.py) runs alongside the MCP stdio server so OpenCode plugin "
            "hooks can trigger memory operations via plain fetch() without waking the LLM: "
            "hooks → http://127.0.0.1:8890/api/* → the same Python functions registered as "
            "MCP tools → MemoryDB. stdlib http.server + threading, localhost-only, port "
            "overridable via AUTOMEM_API_PORT.",
            "sidecar-8890",
            ["sidecar", "8890", "api_server", "hooks"],
            "docs/architecture/ARCHITECTURE.md",
        ),
        dec(
            "Decision (MEM-03): background dream with cooldown. The dream cycle of the "
            "L0_to_L4 consolidation daemon schedules background summarization of stale "
            "layers, but never more often than the cooldown window; state (last_dream, "
            "total_dreams, turn_count) persists in state.json under the L4 narrative path. "
            "In M2 the scope-global dream promotions are hard no-ops (ISO-06) — the "
            "cooldown machinery stays so the cadence contract is preserved.",
            "dream-cooldown",
            ["dream", "cooldown", "MEM-03"],
            "openspec/specs/consolidation/spec.md",
        ),
        dec(
            "Decision (M2-storage): no sqlite-vec for now. Brute-force cosine over filtered "
            "candidate rows in pure stdlib; documented trigger to revisit: past ~50k points, "
            "health() will report scan_ms and sqlite-vec (or an ANN index) gets evaluated "
            "then. Rationale: the real points table is near-empty and zero dependencies beat "
            "speculative scaling; discussed again in M3 and deferred unchanged.",
            "no-sqlite-vec",
            ["sqlite-vec", "50k points", "scan_ms"],
            "openspec/changes/M2-storage/design.md",
        ),
    ]


# ── Public API ────────────────────────────────────────────────────

def build_docs() -> list[dict]:
    """Pure doc spec (no DB). Order defines ids eval-1..eval-N."""
    docs = _code_docs() + _conversation_docs() + _decision_docs()
    out = []
    for n, d in enumerate(docs, start=1):
        d = dict(d)
        d["id"] = f"eval-{n}"
        out.append(d)
    return out


def build_manifest(docs: list[dict] | None = None) -> dict:
    docs = docs or build_docs()
    return {
        d["id"]: {
            "content": d["content"],
            "source_file": d["source_file"],
            "symbols": d["symbols"],
            "layer": d["layer"],
            "type": d["type"],
        }
        for d in docs
    }


async def build_fixture_db(db_path: str | Path) -> dict:
    """(Re)build the fixture DB at db_path; return the content manifest.

    Idempotent: drops the points table first. Deterministic given the same
    working tree (created_at is wall-clock and intentionally NOT part of the
    manifest).
    """
    db_path = str(db_path)
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DROP TABLE IF EXISTS points")
        conn.commit()
    finally:
        conn.close()

    docs = build_docs()
    db = MemoryDB(db_path, COLLECTION, DIM)
    try:
        await db.ensure_collection()
        await db.upsert_batch(
            [
                {
                    "id": d["id"],
                    "payload": {
                        "content": d["content"],
                        "layer": d["layer"],
                        "agent_scope": "shared",
                        "type": d["type"],
                        "source_file": d["source_file"],
                        "source_symbol": ", ".join(d["symbols"]),
                    },
                    "sparse_vectors": bm25_tokenize(d["content"]),
                }
                for d in docs
            ]
        )
    finally:
        await db.close()
    return build_manifest(docs)
