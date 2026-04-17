# Skill: Research — Web Search & Knowledge Retrieval

> For agents that need to search the web, retrieve papers, or query external knowledge.

## When to Use

When the task requires information beyond your training data or internal memory.

## Available Tools

### Web Search
```
Call your web search tool with:
- query: Specific, focused query (avoid broad questions)
- Use multiple queries for complex topics
```

### Context Assembly from Memory
Before searching externally, check internal memory first:
```
1. vk-cache → request_context(query="What do I know about TOPIC?")
2. If memory has relevant info → use it
3. If not → search externally
4. Save search results: automem → memorize(content, mem_type="fact", scope="domain")
```

## Research Protocol

1. **Check memory first** — don't search what you already know
2. **Search specifically** — narrow queries, not broad questions
3. **Save results** — everything found goes into memory
4. **Cite sources** — always attribute external information
5. **Update memory** — if new info contradicts old memory, note it
