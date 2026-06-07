```markdown
# MCP-agent-memory Development Patterns

> Auto-generated skill from repository analysis

## Overview

This skill covers the core development patterns, coding conventions, and operational workflows for the `MCP-agent-memory` Python codebase. The repository focuses on memory management, entity systems, and operational resilience for agent-based systems. It is organized into modular components, uses conventional commits, and emphasizes maintainability, extensibility, and operational robustness.

## Coding Conventions

- **File Naming:**  
  Use `camelCase` for file names.  
  _Example:_  
  ```
  entityRegistry.py
  qdrantClient.py
  ```

- **Import Style:**  
  Use **relative imports** within modules.  
  _Example:_  
  ```python
  from .embedding import EmbeddingModel
  from ..shared.entity_registry import EntityRegistry
  ```

- **Export Style:**  
  Use **named exports** in `__init__.py` to expose module components.  
  _Example (`src/shared/__init__.py`):_  
  ```python
  from .entity_registry import EntityRegistry
  from .relation_manager import RelationManager

  __all__ = ["EntityRegistry", "RelationManager"]
  ```

- **Commit Message Style:**  
  Use [Conventional Commits](https://www.conventionalcommits.org/) with prefixes: `feat`, `fix`, `chore`, `docs`.  
  _Example:_  
  ```
  feat: add timeline export to entity system
  fix: restore event mapping in consolidation server
  ```

## Workflows

### Feature Implementation Across Module
**Trigger:** When adding a new capability, event type, or backend option to an existing module  
**Command:** `/new-feature`

1. Edit or create main implementation file(s) in the relevant module directory (e.g., `src/L0_capture/server/main.py`).
2. Update or create related shared files (e.g., `src/shared/embedding.py`, `src/shared/llm/config.py`).
3. Optionally add or update scripts or configuration (e.g., `scripts/lifecycle.sh`, `etc/launchd/*.plist`).
4. Document or verify the change as needed.

_Example:_
```python
# src/shared/embedding.py
class NewEmbeddingModel:
    def embed(self, text):
        # Implementation here
        pass
```

### Ops Scheduling and Resilience Hardening
**Trigger:** When automating operational tasks or adding resilience features  
**Command:** `/add-ops-task`

1. Create or update shell scripts in `scripts/` (e.g., `backup-data.sh`, `lifecycle.sh`).
2. Create or update launchd plist files in `etc/launchd/`.
3. Optionally update Python health check or related operational code (e.g., `src/shared/health.py`).
4. Document the operational change (e.g., `docs/RUNBOOK.md`).

_Example:_
```bash
# scripts/backup-data.sh
#!/bin/bash
tar czf backup.tar.gz /data/memory
```

### Entity System Extension or Export
**Trigger:** When extending the entity system or making its components importable elsewhere  
**Command:** `/extend-entity-system`

1. Add or update entity system files in `src/shared/` (e.g., `entity_registry.py`, `entity_timeline.py`).
2. Optionally update governance or server files (e.g., `src/governance/server.py`).
3. Update `src/shared/__init__.py` to export new components.

_Example:_
```python
# src/shared/entity_registry.py
class EntityRegistry:
    def register(self, entity):
        # Registration logic
        pass
```
```python
# src/shared/__init__.py
from .entity_registry import EntityRegistry
__all__ = ["EntityRegistry"]
```

### Bugfix in Core Module
**Trigger:** When fixing a regression or mapping error in a main service  
**Command:** `/fix-bug`

1. Edit the main implementation file in the affected module (e.g., `src/L0_to_L4_consolidation/server/main.py`).
2. Restore or correct function definitions or mappings.
3. Verify the fix via compile, runtime, or probe.
4. Optionally add logging or warnings for future issues.

_Example:_
```python
# src/L0_to_L4_consolidation/server/main.py
def map_event(event):
    if event.type not in EVENT_MAP:
        logger.warning(f"Unknown event type: {event.type}")
        return None
    return EVENT_MAP[event.type](event)
```

## Testing Patterns

- **Test File Naming:**  
  Test files follow the `*.test.*` pattern, e.g., `embedding.test.py`.

- **Framework:**  
  The testing framework is not explicitly specified; use standard Python testing tools such as `pytest` or `unittest`.

- **Test Example:**  
  ```python
  # src/shared/embedding.test.py
  import unittest
  from .embedding import EmbeddingModel

  class TestEmbeddingModel(unittest.TestCase):
      def test_embed(self):
          model = EmbeddingModel()
          result = model.embed("test")
          self.assertIsNotNone(result)
  ```

## Commands

| Command           | Purpose                                                      |
|-------------------|--------------------------------------------------------------|
| /new-feature      | Start a new feature or capability across modules             |
| /add-ops-task     | Add or update operational scripts or scheduling              |
| /extend-entity-system | Extend or export new parts of the entity system          |
| /fix-bug          | Fix a bug in a core service module                          |
```
