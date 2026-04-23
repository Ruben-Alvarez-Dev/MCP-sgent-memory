# Phase 3: Unified Server Rewrite

**Duration**: 1-2 days
**Depends on**: Phase 2 complete
**Goal**: Unified server uses public API only — zero private API access

---

## Spec

### 3.1 Current (Broken) Pattern

```python
# Uses private API — fragile, breaks on library updates
for tool_name, tool in module_mcp._tool_manager._tools.items():
    mcp.add_tool(tool.fn, name=f"{prefix}_{tool_name}")
```

### 3.2 New Pattern

```python
# unified/server/main.py
from mcp.server.fastmcp import FastMCP
from shared.config import Config
from shared.qdrant_client import QdrantClient

mcp = FastMCP("MCP-agent-memory")
config = Config.from_env()
qdrant = QdrantClient(config.qdrant_url, "automem", config.embedding_dim)

# Each module registers its tools via public API
from automem.tools import register_tools as automem_register
automem_register(mcp, qdrant, config, prefix="automem_")

from autodream.tools import register_tools as autodream_register
autodream_register(mcp, qdrant, config, prefix="autodream_")

# ... repeat for all 7 modules

mcp.run(transport="stdio")
```

### 3.3 Benefits

- No private API access
- Explicit tool registration
- Easy to understand and debug
- Each module can have different Qdrant collections
- Configurable per-module setup

## Checklist

- [ ] Rewrite unified/server/main.py
- [ ] Remove all `_tool_manager` references
- [ ] Test: unified server starts
- [ ] Test: all 51 tools callable
- [ ] Test: tool names unchanged
- [ ] Update install.sh if needed

## Acceptance Criteria

- [ ] Zero references to `_tool_manager`, `._tools`, or any private FastMCP API
- [ ] Unified server loads 7/7 modules
- [ ] 51 tools registered
- [ ] Tool names identical to pre-refactoring
- [ ] install.sh generates working mcp.json
