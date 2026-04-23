# Phase 2: Server Refactoring

**Duration**: 3-4 days
**Depends on**: Phase 1 complete
**Goal**: Each server module uses shared infrastructure instead of reimplementing boilerplate

---

## Spec

### 2.1 Pattern: Each Module Exports `register_tools()`

Every server module changes from:
```python
mcp = FastMCP("automem")
QDRANT_URL = os.getenv(...)
async def ensure_collection(): ...
async def embed_text(): ...
@mcp.tool()
async def memorize(...): ...
def main(): mcp.run()
```

To:
```python
# automem/tools.py
from shared.qdrant_client import QdrantClient
from shared.config import Config

async def memorize(qdrant: QdrantClient, config: Config, ...) -> MemorizeResult:
    ...

def register_tools(mcp: FastMCP, qdrant: QdrantClient, config: Config, prefix: str = ""):
    mcp.add_tool(lambda **kw: memorize(qdrant, config, **kw), name=f"{prefix}memorize")
    mcp.add_tool(lambda **kw: ingest_event(qdrant, config, **kw), name=f"{prefix}ingest_event")
    # ... all tools

# automem/server/main.py (standalone mode)
from automem.tools import register_tools
mcp = FastMCP("automem")
qdrant = Config.from_env().qdrant_client("automem")
register_tools(mcp, qdrant)
mcp.run()
```

### 2.2 Module-by-Module Refactoring

| Module | Tools to Refactor | Special Considerations |
|--------|------------------|----------------------|
| automem | memorize, ingest_event, heartbeat, status | JSONL append, staging buffer |
| autodream | heartbeat, consolidate, dream, status, get_consolidated, get_semantic | State file, LLM integration, diff mining |
| vk-cache | request_context, check_reminders, push_reminder, dismiss_reminder, detect_context_shift, status, verify_compliance_tool | Retrieval router, compliance |
| conversation-store | save_conversation, get_conversation, search_conversations, list_threads, status | Own collection |
| mem0 | add_memory, search_memory, get_all_memories, delete_memory, status | Own collection |
| engram | save_decision, search_decisions, get_decision, list_decisions, delete_decision, status, vault_write, vault_process_inbox, vault_integrity_check, vault_list_notes, vault_read_note, get_model_pack, set_model_pack, list_model_packs | Filesystem-based, vault |
| sequential-thinking | sequential_thinking, record_thought, create_plan, update_plan_step, reflect, get_thinking_session, list_thinking_sessions, propose_change_set, apply_sandbox, status | Filesystem state, staging buffer |

### 2.3 File Structure per Module

```
automem/
├── __init__.py
├── tools.py          ← NEW: tool functions + register_tools()
├── server/
│   ├── __init__.py
│   └── main.py       ← SIMPLIFIED: just creates MCP, calls register, runs
```

## Checklist

- [ ] Refactor automem (4 tools)
- [ ] Refactor autodream (6 tools)
- [ ] Refactor vk-cache (7 tools)
- [ ] Refactor conversation-store (5 tools)
- [ ] Refactor mem0 (5 tools)
- [ ] Refactor engram (14 tools)
- [ ] Refactor sequential-thinking (10 tools)
- [ ] Each module tested standalone
- [ ] Each module exports register_tools()

## Acceptance Criteria

- [ ] Each server runs standalone with `python -m <module>.server.main`
- [ ] Zero raw `httpx` calls in server modules (all via QdrantClient)
- [ ] Zero `os.getenv()` in server modules (all via Config)
- [ ] All 51 tools produce identical output to pre-refactoring
- [ ] Each module has a `tools.py` with register_tools()
