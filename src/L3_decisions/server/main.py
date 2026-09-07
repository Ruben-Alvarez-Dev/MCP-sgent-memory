"""L3_decisions — Semantic Decision Memory."""
from __future__ import annotations
from datetime import datetime, UTC
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from shared.env_loader import load_env; load_env()
from shared.config import Config
from shared.identity import bind_identity
from shared.result_models import (
    DecisionListResult,
    L3DecisionsStatusResult,
    ModelPackListResult,
    ModelPackResult,
    SaveDecisionResult,
    VaultIntegrityResult,
    VaultNotesResult,
    VaultWriteResult,
)
from shared.sanitize import SanitizeError, sanitize_filename, validate_save_decision, validate_vault_write
from shared.scope import ScopeError, assert_contained, iter_namespaced_files, normalize_scope, scope_subdir

config = Config.from_env()
DECISIONS_PATH = Path(config.L3_decisions_path) if config.L3_decisions_path else Path("")
VAULT_PATH = Path(config.Lx_persistent_path) if config.Lx_persistent_path else Path("")
IDENTITY = bind_identity()  # M4/M5: strict mode raises here (fail-closed boot, ISO-14)
mcp = FastMCP("L3_decisions")

def _assert_path_access(file_path: str) -> Path:
    """Resolve and authorize a caller-supplied decision path (M5/H3).

    Replaces the legacy `str(p).startswith(str(root))` prefix check — under
    that check `/data/decisions-evil` passes against `/data/decisions`.
    `assert_contained` resolves symlinks and uses Path.relative_to, so only
    real containment passes. Additionally, paths landing under `_scopes/<x>/`
    must belong to the caller's bound scope when the server is bound: foreign
    namespaces raise ScopeError BEFORE any read/delete.
    """
    root = DECISIONS_PATH.resolve()
    p = assert_contained(Path(file_path).resolve(), root)
    if IDENTITY.mode == "bound":
        rel = p.relative_to(root)
        if rel.parts and rel.parts[0] == "_scopes" and len(rel.parts) > 1:
            owner = rel.parts[1]
            if owner != IDENTITY.agent_id:
                raise ScopeError(
                    f"path belongs to foreign scope {owner!r} "
                    f"(caller bound as {IDENTITY.agent_id!r}, ISO-13)"
                )
    return p

def _files(agent_scope: str = "shared"):
    """ISO-04 enforced: shared tree (minus _scopes/) + own scope dir. Never siblings."""
    DECISIONS_PATH.mkdir(parents=True, exist_ok=True)
    files = iter_namespaced_files(DECISIONS_PATH, agent_scope, "*.md")
    return sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)

def _read(f):
    c = f.read_text(encoding="utf-8")
    return {"file_path":str(f),"filename":f.name,"content":c,"size":len(c)}

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
async def save_decision(title: str, content: str = "", category: str = "general", tags: str = "", scope: str = "agent", body: str = "") -> SaveDecisionResult:
    """Save an architectural decision as a Markdown file (scoped: non-shared scopes are namespaced)."""
    # M5/H3: identity gate BEFORE any I/O (ISO-13). In bound mode a foreign
    # scope is an isolation violation and MUST raise; in open mode there is no
    # identity to violate, so a malformed scope keeps the legacy error payload
    # (ISO-03 contract: save_decision answers status="error", never writes).
    try:
        scope = IDENTITY.assert_agent(scope)
    except ScopeError as e:
        if IDENTITY.mode == "bound":
            raise
        return SaveDecisionResult(status="error", file_path="", title=title, error=str(e))
    try:
        # If body is provided and content is empty, use body as content
        effective_content = body if body else content
        # Validate the RAW scope first: sanitizers neutralize traversal by
        # remapping ("../../etc" -> "etc"), which would silently redirect the
        # write into another tenant's namespace. Strict check first, sanitize after.
        ns = normalize_scope(scope)
        clean = validate_save_decision(title, effective_content, category, tags, ns)
    except (SanitizeError, ValueError) as e:
        return SaveDecisionResult(status="error", file_path="", title=title, error=str(e))
    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    fn = sanitize_filename(f"{ts}-{clean['title'][:50]}")
    td = scope_subdir(DECISIONS_PATH, ns) / clean["category"]; td.mkdir(parents=True, exist_ok=True)
    fp = td / f"{fn}.md"
    md = f"---\ntitle: \"{clean['title']}\"\ncategory: {clean['category']}\ntags: {clean['tags']}\nscope: {ns}\n---\n\n# {clean['title']}\n\n{effective_content}\n"
    fp.write_text(md, encoding="utf-8")
    return SaveDecisionResult(status="saved", file_path=str(fp), title=clean["title"])

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def search_decisions(query: str, category: str = "", limit: int = 10, agent_scope: str = "shared") -> DecisionListResult:
    """Search decisions by keyword matching (token-based, scoped: own + shared only)."""
    agent_scope = IDENTITY.assert_agent(agent_scope)  # M5/H3: identity gate before I/O (ISO-13)
    import re
    tokens = [t.lower() for t in re.split(r'\s+', query) if len(t) > 1]
    if not tokens:
        return DecisionListResult(count=0, decisions=[])
    results = []
    for f in _files(agent_scope):
        if category and category not in str(f): continue
        try:
            content_lower = f.read_text(encoding="utf-8").lower()
            if all(t in content_lower for t in tokens):
                results.append({"file_path":str(f),"filename":f.name})
        except OSError: pass
        if len(results) >= limit: break
    return DecisionListResult(count=len(results), decisions=results)

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def get_decision(file_path: str) -> dict:
    """Get a specific decision by file path."""
    try:
        p = _assert_path_access(file_path)  # M5/H3: real containment, no prefix bug
    except ScopeError as e:
        return {"status": "forbidden", "error": str(e)}
    return _read(p) if p.exists() else {"status":"not_found"}

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def list_decisions(category: str = "", scope: str = "", limit: int = 20) -> DecisionListResult:
    """List decisions with optional filtering (scoped: own + shared only)."""
    # M5/H3: identity gate before I/O; empty scope follows the ISO-15 default
    # coercion (bound→own scope, open→legacy 'default' tenant).
    scope = IDENTITY.assert_agent(scope or "default")
    files = _files(scope)
    if category: files = [f for f in files if category in str(f)]
    return DecisionListResult(count=len(files[:limit]), decisions=[_read(f) for f in files[:limit]])

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True))
async def delete_decision(file_path: str) -> dict:
    """Delete a decision file."""
    # M5/H3: ScopeError propagates — a destructive call fails closed on jail
    # escape or foreign-scope ownership instead of returning a soft payload.
    p = _assert_path_access(file_path)
    if p.exists():
        p.unlink()
        return {"status": "deleted"}
    return {"status": "not_found"}

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
async def vault_write(folder: str, filename: str, content: str, tags: str = "") -> VaultWriteResult:
    """Write a note to the Obsidian vault."""
    clean = validate_vault_write(folder, filename, content, tags)
    target = VAULT_PATH / clean["folder"]; target.mkdir(parents=True, exist_ok=True)
    fp = target / f"{clean['filename']}.md"
    md = f"---\ntags: {clean['tags']}\ncreated: {datetime.now(UTC).isoformat()}\n---\n\n{clean['content']}\n"
    fp.write_text(md, encoding="utf-8")
    return VaultWriteResult(status="written", path=str(fp))

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def vault_process_inbox() -> dict:
    inbox = VAULT_PATH / "Inbox"
    if not inbox.exists(): return {"status":"no_inbox"}
    return {"status":"processed","count":len(list(inbox.glob("*.md")))}

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def vault_integrity_check() -> VaultIntegrityResult:
    if not VAULT_PATH.exists(): return VaultIntegrityResult(status="vault_not_found")
    return VaultIntegrityResult(status="ok", total_notes=sum(1 for _ in VAULT_PATH.rglob("*.md")))

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def vault_list_notes(folder: str = "") -> VaultNotesResult:
    base = VAULT_PATH / folder if folder else VAULT_PATH
    if not base.exists(): return VaultNotesResult(count=0)
    notes = [{"name":f.name,"path":str(f)} for f in sorted(base.rglob("*.md"))]
    return VaultNotesResult(count=len(notes), notes=notes[:50])

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def vault_read_note(folder: str, filename: str) -> dict:
    fp = VAULT_PATH / folder / f"{filename}.md"
    return {"content":fp.read_text(encoding="utf-8")} if fp.exists() else {"status":"not_found"}

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def get_model_pack(name: str = "default") -> ModelPackResult:
    pf = DECISIONS_PATH / "model-packs" / f"{name}.yaml"
    return ModelPackResult(name=name, content=pf.read_text()) if pf.exists() else ModelPackResult(name=name, status="not_found")

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
async def set_model_pack(name: str, content: str) -> ModelPackResult:
    safe_name = sanitize_filename(name, field="model_pack_name")
    d = DECISIONS_PATH / "model-packs"; d.mkdir(parents=True, exist_ok=True)
    (d / f"{safe_name}.yaml").write_text(content, encoding="utf-8")
    return ModelPackResult(name=safe_name, status="set")

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def list_model_packs() -> ModelPackListResult:
    d = DECISIONS_PATH / "model-packs"
    return ModelPackListResult(packs=[f.stem for f in d.glob("*.yaml")] if d.exists() else [])

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def status() -> L3DecisionsStatusResult:
    vc = sum(1 for _ in VAULT_PATH.rglob("*.md")) if VAULT_PATH.exists() else 0
    return L3DecisionsStatusResult(daemon="L3_decisions", status="RUNNING", decision_files=len(_files()), vault_notes=vc)

def register_tools(target_mcp, target_config, prefix=""):
    global config, DECISIONS_PATH, VAULT_PATH
    config = target_config
    DECISIONS_PATH = Path(config.L3_decisions_path) if config.L3_decisions_path else Path("")
    VAULT_PATH = Path(config.Lx_persistent_path) if config.Lx_persistent_path else Path("")
    for fn in [save_decision,search_decisions,get_decision,list_decisions,delete_decision,vault_write,vault_process_inbox,vault_integrity_check,vault_list_notes,vault_read_note,get_model_pack,set_model_pack,list_model_packs,status]:
        target_mcp.add_tool(fn, name=f"{prefix}{fn.__name__}")

def main(): mcp.run(transport="stdio")
if __name__ == "__main__": main()
