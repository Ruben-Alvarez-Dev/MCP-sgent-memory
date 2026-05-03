"""Engram — Semantic Decision Memory (L3)."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from shared.env_loader import load_env; load_env()
from shared.config import Config
from shared.sanitize import validate_save_decision, validate_vault_write, sanitize_filename, sanitize_text, sanitize_thread_id, validate_json_field
from shared.result_models import SaveDecisionResult, DecisionListResult, VaultWriteResult, VaultIntegrityResult, VaultNotesResult, ModelPackResult, ModelPackListResult, EngramStatusResult

config = Config.from_env()
ENGRAM_PATH = Path(config.engram_path) if config.engram_path else Path("")
VAULT_PATH = Path(config.vault_path) if config.vault_path else Path("")
mcp = FastMCP("L3_decisions")

def _files():
    ENGRAM_PATH.mkdir(parents=True, exist_ok=True)
    return sorted(ENGRAM_PATH.rglob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)

def _read(f):
    c = f.read_text(encoding="utf-8")
    return {"file_path":str(f),"filename":f.name,"content":c,"size":len(c)}

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
async def save_decision(title: str, content: str = "", category: str = "general", tags: str = "", scope: str = "agent", body: str = "") -> SaveDecisionResult:
    """Save an architectural decision as a Markdown file."""
    # If body is provided and content is empty, use body as content
    effective_content = body if body else content
    clean = validate_save_decision(title, effective_content, category, tags, scope)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    fn = sanitize_filename(f"{ts}-{clean['title'][:50]}")
    td = ENGRAM_PATH / clean["category"]; td.mkdir(parents=True, exist_ok=True)
    fp = td / f"{fn}.md"
    md = f"---\ntitle: \"{clean['title']}\"\ncategory: {clean['category']}\ntags: {clean['tags']}\n---\n\n# {clean['title']}\n\n{effective_content}\n"
    fp.write_text(md, encoding="utf-8")
    return SaveDecisionResult(status="saved", file_path=str(fp), title=clean["title"])

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def search_decisions(query: str, category: str = "", limit: int = 10) -> DecisionListResult:
    """Search decisions by keyword matching (token-based)."""
    import re
    tokens = [t.lower() for t in re.split(r'\s+', query) if len(t) > 1]
    if not tokens:
        return DecisionListResult(count=0, decisions=[])
    results = []
    for f in _files():
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
    p = Path(file_path).resolve()
    engram_root = ENGRAM_PATH.resolve()
    if not str(p).startswith(str(engram_root)):
        return {"status": "forbidden", "error": "Path outside engram root"}
    return _read(p) if p.exists() else {"status":"not_found"}

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def list_decisions(category: str = "", scope: str = "", limit: int = 20) -> DecisionListResult:
    """List decisions with optional filtering."""
    files = _files()
    if category: files = [f for f in files if category in str(f)]
    return DecisionListResult(count=len(files[:limit]), decisions=[_read(f) for f in files[:limit]])

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True))
async def delete_decision(file_path: str) -> dict:
    """Delete a decision file."""
    p = Path(file_path).resolve()
    engram_root = ENGRAM_PATH.resolve()
    if not str(p).startswith(str(engram_root)):
        return {"status": "forbidden", "error": "Path outside engram root"}
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
    md = f"---\ntags: {clean['tags']}\ncreated: {datetime.now(timezone.utc).isoformat()}\n---\n\n{clean['content']}\n"
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
    pf = ENGRAM_PATH / "model-packs" / f"{name}.yaml"
    return ModelPackResult(name=name, content=pf.read_text()) if pf.exists() else ModelPackResult(name=name, status="not_found")

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
async def set_model_pack(name: str, content: str) -> ModelPackResult:
    safe_name = sanitize_filename(name, field="model_pack_name")
    d = ENGRAM_PATH / "model-packs"; d.mkdir(parents=True, exist_ok=True)
    (d / f"{safe_name}.yaml").write_text(content, encoding="utf-8")
    return ModelPackResult(name=safe_name, status="set")

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def list_model_packs() -> ModelPackListResult:
    d = ENGRAM_PATH / "model-packs"
    return ModelPackListResult(packs=[f.stem for f in d.glob("*.yaml")] if d.exists() else [])

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def status() -> EngramStatusResult:
    vc = sum(1 for _ in VAULT_PATH.rglob("*.md")) if VAULT_PATH.exists() else 0
    return EngramStatusResult(daemon="engram", status="RUNNING", engram_files=len(_files()), vault_notes=vc)

def register_tools(target_mcp, _qdrant, target_config, prefix=""):
    global config, ENGRAM_PATH, VAULT_PATH
    config = target_config
    ENGRAM_PATH = Path(config.engram_path) if config.engram_path else Path("")
    VAULT_PATH = Path(config.vault_path) if config.vault_path else Path("")
    for fn in [save_decision,search_decisions,get_decision,list_decisions,delete_decision,vault_write,vault_process_inbox,vault_integrity_check,vault_list_notes,vault_read_note,get_model_pack,set_model_pack,list_model_packs,status]:
        target_mcp.add_tool(fn, name=f"{prefix}{fn.__name__}")

def main(): mcp.run(transport="stdio")
if __name__ == "__main__": main()
