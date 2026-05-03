# MCP-agent-memory v2.0.0 — Lx Naming Scheme, Bilingual Vault & Full English Docs

## 🎯 Overview
This release standardizes all module naming to the Lx layer convention (L0-L5), introduces bilingual vault support (English code + Spanish Obsidian UI), and translates all documentation from Spanish to English.

## 🔄 Breaking Changes

### Module Naming Standardization
All modules now follow the Lx layer naming scheme:

| Old Name | New Name |
|----------|----------|
| automem | L0_capture |
| autodream | L0_to_L4_consolidation |
| vk-cache / vk_cache | L5_routing |
| conversation-store | L2_conversations |
| mem0 | L3_facts |
| engram | L3_decisions |
| sequential-thinking | Lx_reasoning |

### Qdrant Collection Names
| Old Collection | New Collection |
|----------------|----------------|
| automem | L0_L4_memory |
| conversations | L2_conversations |
| mem0_memories | L3_facts |

### Tool Prefixes
All MCP tools now use standardized prefixes:
- `L0_capture_*` — Event capture and heartbeats
- `L0_to_L4_consolidation_*` — Memory consolidation and dreams
- `L2_conversations_*` — Conversation storage and search
- `L3_facts_*` — Semantic memory (Mem0 integration)
- `L3_decisions_*` — Decision logging (Engram integration)
- `L5_routing_*` — Context routing and retrieval
- `Lx_reasoning_*` — Sequential thinking and planning

## 📝 Documentation Translation

### Architecture Documents (Translated)
- ✅ `LA-MOCHILA-EXPLICADA.md` → `THE-BACKPACK-EXPLAINED.md` (271 → 280 lines)
- ✅ `LA-MOCHILA-POR-DENTRO.md` → `THE-BACKPACK-INTERNALS.md` (325 → 340 lines)
- ✅ `LA-MOCHILA-4-ANIOS.md` → `THE-BACKPACK-4-YEARS.md` (158 → 165 lines)
- ✅ Updated `ARCHITECTURE.md` with new module names
- ✅ Updated `BENCHMARK-3-ENGINES.md` (verified clean)
- ✅ Updated `embeddings.md` (verified clean)

### Research Papers (Translated)
- ✅ `paper-memoria-contexto-agentes-ia.md` → `paper-memory-context-ai-agents.md` (756 lines)
  - Comprehensive analysis of memory systems for AI agents
  - Comparison of Mem0, Supermemory, Letta, GraphRAG, LightRAG, Cognee, Zep, LangMem
- ✅ `verificacion-continua-conocimiento.md` → `continuous-knowledge-verification.md` (525 lines)
  - Research on knowledge freshness verification
  - Integration plan for MCP-agent-memory v1.4

### All Documentation Now in Professional English
- Zero Spanish characters in production documentation
- Proper markdown formatting
- Cross-references between documents
- Academic tone for research papers
- Technical depth for architecture docs

## 🌍 Bilingual Vault Support

### Vault Constants (English → Spanish)
The vault now supports bilingual naming for seamless Obsidian integration:

| Code Constant | Disk Folder (Obsidian) |
|---------------|------------------------|
| `FOLDER_INBOX` | `Inbox` |
| `FOLDER_DECISIONS` | `Decisiones` |
| `FOLDER_KNOWLEDGE` | `Conocimiento` |
| `FOLDER_EPISODES` | `Episodios` |
| `FOLDER_ENTITIES` | `Entidades` |
| `FOLDER_NOTES` | `Notas` |
| `FOLDER_PEOPLE` | `Personas` |
| `FOLDER_TEMPLATES` | `Plantillas` |

**Implementation**: `src/shared/vault_constants.py` with `to_disk_folder()` method.

## 🔧 Code Changes

### Runtime Code
- Updated `src/shared/api_server.py` — Collection defaults, function names
- Updated `src/shared/retrieval/__init__.py` — Collection defaults
- Updated `src/shared/retrieval/index_repo.py` — Collection defaults
- Updated `src/L2_conversations/server/main.py` — Hardcoded collection name
- Updated `src/unified/server/main_http.py` — Route table

### Configuration & Scripts
- Updated `install/verify.sh` — Module verification
- Updated `install/services.sh` — Collection names
- Updated `scripts/lifecycle.sh` — Collection names

### Documentation
- Fixed broken links in `docs/ROADMAP.md`
- Updated `docs/architecture/THE-BACKPACK-INTERNALS.md`

### Cleanup
- Deleted `docs/PROMPT-DOC-TRANSLATION.md` (temporary prompt file)

## ✅ Quality Assurance

### All Python Compiles
```bash
✓ vault_constants.py
✓ sanitize.py
✓ api_server.py
✓ unified/server/main.py
✓ unified/server/main_http.py
```

### No Broken Links
All internal documentation links verified. No references to:
- ❌ `LA-MOCHILA-*.md`
- ❌ `paper-memoria-contexto-agentes-ia.md`
- ❌ `verificacion-continua-conocimiento.md`

### Backward Compatibility
- **servers/** directory maintains old structure for migration
- `docs/archive/` preserves historical Spanish documentation
- Environment variables `QDRANT_COLLECTION`, `CONV_COLLECTION`, `MEM0_COLLECTION` still work

## 📊 Statistics

| Metric | Value |
|--------|-------|
| Documentation lines translated | ~7,000 |
| Files renamed | 5 |
| Files translated | 5 |
| Files modified | 13 |
| Module names standardized | 7 |
| Collection names updated | 3 |
| Tool prefixes updated | 7 |

## 🚀 Installation

```bash
# Clone or update
git clone https://github.com/Ruben-Alvarez-Dev/MCP-agent-memory.git
cd MCP-agent-memory

# Install dependencies
./install.sh

# Verify installation
python -m src.unified.server.main --version
```

## 📖 Documentation

- [Architecture Overview](https://github.com/Ruben-Alvarez-Dev/MCP-agent-memory/blob/main/docs/architecture/ARCHITECTURE.md)
- [The Backpack Explained](https://github.com/Ruben-Alvarez-Dev/MCP-agent-memory/blob/main/docs/architecture/THE-BACKPACK-EXPLAINED.md)
- [The Backpack Internals](https://github.com/Ruben-Alvarez-Dev/MCP-agent-memory/blob/main/docs/architecture/THE-BACKPACK-INTERNALS.md)
- [Memory & Context Research Paper](https://github.com/Ruben-Alvarez-Dev/MCP-agent-memory/blob/main/docs/research/paper-memory-context-ai-agents.md)
- [Continuous Knowledge Verification](https://github.com/Ruben-Alvarez-Dev/MCP-agent-memory/blob/main/docs/research/continuous-knowledge-verification.md)

## 🤝 Contributing

See [CONTRIBUTING.md](https://github.com/Ruben-Alvarez-Dev/MCP-agent-memory/blob/main/CONTRIBUTING.md) for guidelines.

## 🔗 Related Releases

- [CLI-agent-memory v1.1.0](https://github.com/Ruben-Alvarez-Dev/CLI-agent-memory/releases/tag/v1.1.0) — Corresponding CLI adapter release

---

**Full Changelog**: https://github.com/Ruben-Alvarez-Dev/MCP-agent-memory/compare/v1.2.0...v2.0.0
