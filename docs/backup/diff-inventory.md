# Diff Inventory: MCP-servers/ vs src/

## Servers

### automem
Status: DEGRADED (complete=     371, skeleton=      59)

### autodream
Status: DEGRADED (complete=     644, skeleton=      60)

### vk-cache
Status: DEGRADED (complete=     600, skeleton=     102)

### engram
Status: DEGRADED (complete=     428, skeleton=      50)

### mem0
Status: IDENTICAL (     246 lines)

### sequential-thinking
Status: MISSING from src/ (complete=     522 lines)

### conversation-store
Status: MISSING from src/ (complete=     196 lines)

## Shared Modules

### shared/__init__.py
Status: MISSING from src/shared/ (       4 lines)

### shared/compliance/__init__.py
Status: MISSING from src/shared/ (     293 lines)

### shared/diff_sandbox.py
Status: IDENTICAL (     461 lines)

### shared/embedding.py
Status: DIFFERENT (complete=     615, current=     847)

### shared/env_loader.py
Status: MISSING from src/shared/ (     193 lines)

### shared/llm/__init__.py
Status: MISSING from src/shared/ (      42 lines)

### shared/llm/base.py
Status: MISSING from src/shared/ (     164 lines)

### shared/llm/config.py
Status: DIFFERENT (complete=     358, current=      79)

### shared/llm/llama_cpp.py
Status: MISSING from src/shared/ (     341 lines)

### shared/llm/lmstudio.py
Status: MISSING from src/shared/ (     210 lines)

### shared/llm/ollama.py
Status: MISSING from src/shared/ (     189 lines)

### shared/models/__init__.py
Status: DIFFERENT (complete=     277, current=       0)

### shared/models/repo.py
Status: DIFFERENT (complete=      28, current=       8)

### shared/observe.py
Status: MISSING from src/shared/ (     443 lines)

### shared/retrieval/__init__.py
Status: DIFFERENT (complete=     412, current=     228)

### shared/retrieval/code_map.py
Status: DIFFERENT (complete=     664, current=     175)

### shared/retrieval/index_repo.py
Status: DIFFERENT (complete=     263, current=     116)

### shared/retrieval/pruner.py
Status: MISSING from src/shared/ (     135 lines)

### shared/retrieval/repo_map.py
Status: DIFFERENT (complete=     182, current=       1)

### shared/sanitize.py
Status: IDENTICAL (     649 lines)

### shared/vault_manager/__init__.py
Status: MISSING from src/shared/ (     758 lines)

