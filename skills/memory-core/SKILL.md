# Skill: Memory Core — Universal Agent Memory

> Any agent, any session, zero configuration.
> This skill tells you EXACTLY how to use the memory system without thinking.

## When to Use

Use this skill in **every conversation**. The memory system works whether you're
connected or disconnected — but you need to participate in the protocol.

## The Protocol (Bidirectional)

```
YOU ←→ MEMORY SYSTEM
  PULL: request_context()     → get relevant context
  PUSH: check_reminders()     → see if memory has something to tell you
```

## Step-by-Step (Every Turn)

### 1. Start of Turn — Check Reminders
```
Call: vk-cache → check_reminders(agent_id="YOUR_ID")
If there are reminders → read them before answering
If not relevant → dismiss with dismiss_reminder(reminder_id)
```

### 2. If You Need Context — Request It
```
Call: vk-cache → request_context(
    query="What do I know about X?",
    agent_id="YOUR_ID",
    intent="answer|plan|debug|review",
    token_budget=8000
)
```

### 3. If Context Shifted — Detect It
```
Call: vk-cache → detect_context_shift(
    current_query="What I'm asking now",
    previous_query="What I asked before"
)
```

### 4. Save Important Facts — Memorize
```
Call: automem → memorize(
    content="The decision we just made about X",
    mem_type="decision|fact|preference|episode",
    scope="session|agent|domain|personal",
    scope_id="current-context",
    importance=0.8,
    tags="tag1, tag2"
)
```

### 5. Save the Conversation — Record Thread
```
Call: conversation-store → save_conversation(
    thread_id="unique-thread-id",
    messages_json='[{"role": "user", "content": "..."}, ...]'
)
```

### 6. Heartbeat — Signal You're Alive
```
Call: automem → heartbeat(
    agent_id="YOUR_ID",
    session_id="current-session",
    turn_count=N
)
```

## Memory Layers (Know Where Things Live)

| Layer | What | Where | Frequency |
|-------|------|-------|-----------|
| L0 RAW | Audit trail, all events | JSONL file | Every event |
| L1 WORKING | Hot facts, recent steps | Qdrant | Every turn |
| L2 EPISODIC | Conversation threads, incidents | Qdrant | Every 10 turns |
| L3 SEMANTIC | Decisions, entities, patterns | Engram + Qdrant | Every hour |
| L4 CONSOLIDATED | Summaries, narratives, dreams | Qdrant | Nightly |
| L5 CONTEXT | What you see (ephemeral packs) | Assembled on demand | Per request |

## Rules

1. **Always check reminders** before asking for context
2. **Always save decisions** — they're the most valuable memory
3. **Always heartbeat** — otherwise the system thinks you're dead
4. **Don't dump everything into memory** — only what's worth remembering
5. **If you use a context pack, cite it** — the system tracks what's useful
6. **If you ignore a reminder, dismiss it** — the system learns

## Agent Backpack

You have your own isolated memory space. Your `agent_id` determines what you see:

```
- session/current   → What's happening now
- agent/YOUR_ID     → Your personal knowledge
- domain/YOUR_DOMAIN → Domain expertise
- personal/USER     → User preferences
- global-core       → Universal rules (small!)
```

You CANNOT see other agents' memories unless they're in shared domains.

## Quick Reference

| Action | Tool | Server |
|--------|------|--------|
| Get context | `request_context` | vk-cache |
| Check reminders | `check_reminders` | vk-cache |
| Save memory | `memorize` | automem |
| Save conversation | `save_conversation` | conversation-store |
| Search conversations | `search_conversations` | conversation-store |
| Search semantic | `search_memory` | mem0-bridge |
| Search decisions | `search_decisions` | engram-bridge |
| Send heartbeat | `heartbeat` | automem |
| Detect context shift | `detect_context_shift` | vk-cache |
