# Phase 4: MCP Compliance

**Duration**: 1-2 days
**Depends on**: Phase 3 complete
**Goal**: Full MCP protocol compliance — structured output, annotations, resources

---

## Spec

### 4.1 Structured Output via Pydantic

Every tool returns a Pydantic model instead of a JSON string.

```python
from pydantic import BaseModel

class MemorizeResult(BaseModel):
    status: str
    memory_id: str
    layer: str
    scope: str

@mcp.tool()
async def memorize(content: str, ...) -> MemorizeResult:
    ...
    return MemorizeResult(status="stored", memory_id=item.memory_id, ...)
```

FastMCP serializes the return type automatically as MCP structured output.

### 4.2 Tool Annotations

```python
from mcp.types import ToolAnnotations

@mcp.tool(annotations=ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    openWorldHint=False,
))
async def memorize(content: str, ...) -> MemorizeResult:
    ...
```

### 4.3 Resources (Optional)

```python
@mcp.resource("memory://status")
async def memory_status() -> str:
    """Current memory system status."""
    return json.dumps({...})
```

### 4.4 Return Models per Module

| Module | Models Needed |
|--------|-------------|
| automem | MemorizeResult, IngestResult, HeartbeatResult, StatusResult |
| autodream | ConsolidateResult, DreamResult, StatusResult |
| vk-cache | ContextPackResult, ReminderResult, StatusResult |
| conversation-store | SaveResult, SearchResult, ListResult |
| mem0 | AddResult, SearchResult, ListResult |
| engram | SaveDecisionResult, SearchResult, VaultResult |
| sequential-thinking | ThinkingResult, PlanResult, ReflectResult |

## Checklist

- [ ] Define Pydantic return models for all 51 tools
- [ ] Update all tools to return Pydantic models
- [ ] Add MCP annotations to all tools
- [ ] Add @mcp.resource() for status endpoints
- [ ] Test: structured output works in Pi/Claude

## Acceptance Criteria

- [ ] All 51 tools have typed Pydantic return models
- [ ] All tools have MCP annotations
- [ ] No tool returns raw JSON string (all return Pydantic models)
- [ ] Status resources available via @mcp.resource()
