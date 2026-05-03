# Documentation Translation & Restructuring Task

## Context
Both repos have been refactored with a new naming scheme. All code uses English constants. But documentation still contains Spanish content and old module names that need translation.

## Repos
- ~/Code/MCP-agent-memory/
- ~/Code/CLI-agent-memory/

## Naming Rules (MANDATORY - replace ALL old names)

### Module names:
| OLD (NEVER use)        | NEW (ALWAYS use)            |
|------------------------|-----------------------------|
| automem                | L0_capture                  |
| autodream              | L0_to_L4_consolidation      |
| conversation-store     | L2_conversations            |
| mem0                   | L3_facts                    |
| engram                 | L3_decisions                |
| vk-cache / vk_cache    | L5_routing                  |
| sequential-thinking    | Lx_reasoning                |

### Tool prefixes:
| OLD                    | NEW                         |
|------------------------|-----------------------------|
| automem_*              | L0_capture_*                |
| autodream_*            | L0_to_L4_consolidation_*    |
| conversation_store_*   | L2_conversations_*          |
| mem0_*                 | L3_facts_*                  |
| engram_*               | L3_decisions_*              |
| vk_cache_*             | L5_routing_*                |
| sequential_thinking_*  | Lx_reasoning_*              |

### Qdrant Collections:
| OLD              | NEW              |
|------------------|------------------|
| automem          | L0_L4_memory     |
| conversations    | L2_conversations |
| mem0_memories    | L3_facts         |

### Memory Layers:
| Layer | Name        | Type              |
|-------|-------------|-------------------|
| L0    | Sensory     | Raw event capture |
| L1    | Working     | Working memory    |
| L2    | Episodic    | Episodic memory   |
| L3    | Semantic    | Semantic memory   |
| L4    | Narrative   | Consolidated      |
| L5    | Selective   | Context routing   |

### Vault Constants (from src/shared/vault_constants.py):
- Code uses ENGLISH: inbox, decisions, knowledge, episodes, entities, notes, people, templates
- Disk shows SPANISH (for Obsidian): Inbox, Decisiones, Conocimiento, Episodios, Entidades, Notas, Personas, Plantillas
- Translation happens via vault_constants.to_disk_folder()

## Tasks

### MCP-agent-memory/docs/architecture/ (3 files to translate + rename)

1. LA-MOCHILA-EXPLICADA.md (271 lines)
   → RENAME to THE-BACKPACK-EXPLAINED.md
   → TRANSLATE to professional English
   → Keep accessible explanatory tone
   → Replace all old module names
   → This is "The Backpack explained to anyone" - accessible intro to the system

2. LA-MOCHILA-POR-DENTRO.md (325 lines)
   → RENAME to THE-BACKPACK-INTERNALS.md
   → TRANSLATE to professional English
   → Technical deep-dive into how everything connects
   → Replace all old module names

3. LA-MOCHILA-4-ANIOS.md (158 lines)
   → RENAME to THE-BACKPACK-4-YEARS.md
   → TRANSLATE to professional English
   → Historical timeline / roadmap document
   → Replace all old module names

### MCP-agent-memory/docs/research/ (2 files to translate + rename)

4. paper-memoria-contexto-agentes-ia.md
   → RENAME to paper-memory-context-ai-agents.md
   → TRANSLATE to professional English
   → Academic research paper about memory in AI agents
   → Keep citations and references intact
   → When mentioning EXTERNAL tools (like Mem0 project), keep original name
   → When mentioning OUR modules, use new names

5. verificacion-continua-conocimiento.md
   → RENAME to continuous-knowledge-verification.md
   → TRANSLATE to professional English
   → Research on knowledge freshness verification
   → Replace our module names only

### MCP-agent-memory/docs/architecture/ (verify/update - may have Spanish)

6. ARCHITECTURE.md (173 lines) - check for Spanish, translate if needed
7. BENCHMARK-3-ENGINES.md (107 lines) - check for Spanish, translate if needed
8. SPEC-backpack-v1.2.md (122 lines) - check for Spanish, translate if needed
9. embeddings.md (29 lines) - check for Spanish, translate if needed

### CLI-agent-memory/docs/ (1 file to translate + rename, 3 to verify)

10. DECISIONES.md
    → RENAME to DECISIONS.md
    → TRANSLATE to English
    → Replace old module names

11. SPEC-v1.md - check for any remaining Spanish, fix
12. SPEC-v5.md - check for any remaining Spanish, fix
13. CHECKLIST-R1.md - check for any remaining Spanish, fix

## Quality Standards

- Professional technical English
- Proper markdown formatting (headings, tables, code blocks)
- Cross-references between documents
- No dead links
- Consistent terminology
- Code examples where appropriate
- Every document should have a header with: Title, Last Updated date, Status
- Research papers keep academic tone
- Architecture docs keep technical depth
- "The Backpack" docs keep accessible but professional tone

## After Translation

For each repo:
1. git add -A
2. git commit -m "docs: translate all documentation to English, rename files, standardize naming"
3. git push origin main
