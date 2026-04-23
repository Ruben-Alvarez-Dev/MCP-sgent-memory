# Phase 5: Quality & Testing

**Duration**: 2-3 days
**Depends on**: Phase 4 complete
**Goal**: Production-quality code — logging, type hints, error handling, tests

---

## Spec

### 5.1 Replace datetime.utcnow()

All `datetime.utcnow()` → `datetime.now(timezone.utc)` (deprecated in Python 3.12+)

Files affected (15+ instances):
- automem/server/main.py
- autodream/server/main.py
- vk-cache/server/main.py
- shared/models/__init__.py

### 5.2 Replace Bare Excepts

Every `except Exception:` or `except Exception as e:` must include logging:

```python
# Before
except Exception:
    pass

# After
except Exception:
    logger.warning("Qdrant unreachable", exc_info=True)
```

### 5.3 Structured Logging

```python
import logging
logger = logging.getLogger("memory.automem")

# Configure once in config.py
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(name)s %(levelname)s %(message)s'
)
```

### 5.4 Full Type Hints

All public functions must have:
- Parameter type hints
- Return type hints
- No `Any` unless truly dynamic

### 5.5 Fix BM25 Tokenizer

Replace MD5 truncation with proper hashing:
```python
# Before (collision risk)
token_hash = int(hashlib.md5(token.encode()).hexdigest()[:8], 16)

# After
import mmh3  # or use built-in hash() with seed
token_hash = mmh3.hash(token, seed=42) & 0xFFFFFFFF
```

### 5.6 Integration Test

```python
def test_unified_server_loads():
    """Verify unified server loads all 7 modules with 51 tools."""
    from unified.server.main import mcp
    tools = mcp._tool_manager.list_tools()
    assert len(tools) == 51
    for tool in tools:
        assert '_' in tool.name  # has prefix
```

## Checklist

- [ ] Replace all datetime.utcnow() (15+ instances)
- [ ] Replace all bare excepts (23+ instances)
- [ ] Add logging to all modules
- [ ] Add type hints to all public functions
- [ ] Fix BM25 tokenizer hashing
- [ ] Integration test: unified server starts, 51 tools
- [ ] Integration test: each standalone server starts
- [ ] All existing tests pass

## Acceptance Criteria

- [ ] Zero `datetime.utcnow()` calls
- [ ] Zero bare `except Exception:` without logging
- [ ] All public functions have type hints
- [ ] `logging` used instead of `print()`
- [ ] BM25 uses proper hash function
- [ ] All tests pass (existing + new)
