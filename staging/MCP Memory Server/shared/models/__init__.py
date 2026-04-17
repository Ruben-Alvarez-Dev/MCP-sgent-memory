"""Shared data models for all MCP memory servers.

Canonical data contracts used across:
  - automem    (L0/L1/L2 ingest daemon)
  - autodream  (L3/L4 consolidation daemon)
  - vk-cache   (L5 context assembly + bidirectional protocol)
  - conversation-store, mem0-bridge, engram-bridge
  - skills     (agent instruction sets)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────────────────────────


class MemoryLayer(int, Enum):
    """6-layer memory stack."""

    RAW = 0          # Event lake — append-only audit
    WORKING = 1      # Steps, facts, hot dialogue (mem0)
    EPISODIC = 2     # Conversations, incidents, tech episodes
    SEMANTIC = 3     # Decisions, entities, patterns (engram)
    CONSOLIDATED = 4 # Summaries, narratives, dream
    CONTEXT = 5      # Ephemeral context packs (vk-cache)


class MemoryType(str, Enum):
    """Content type of a memory item."""

    # L1 Working
    STEP = "step"
    FACT = "fact"
    PREFERENCE = "preference"

    # L2 Episodic
    EPISODE = "episode"
    CONVERSATION = "conversation"
    BUG_FIX = "bug_fix"
    CONFIG = "config"
    CODE_SNIPPET = "code_snippet"
    ERROR_TRACE = "error_trace"

    # L3 Semantic
    DECISION = "decision"
    ENTITY = "entity"
    RELATION = "relation"
    PATTERN = "pattern"

    # L4 Consolidated
    SUMMARY = "summary"
    NARRATIVE = "narrative"
    DREAM = "dream"

    # L0 Raw
    RAW_EVENT = "raw_event"


class MemoryScope(str, Enum):
    """Namespace scopes for agent backpack isolation."""

    GLOBAL_CORE = "global-core"
    DOMAIN = "domain"
    TEAM = "team"
    TOPIC = "topic"
    PERSONAL = "personal"
    AGENT = "agent"
    SESSION = "session"


class RawEventType(str, Enum):
    """L0 raw event types."""

    TERMINAL = "terminal"
    FILE_ACCESS = "file_access"
    GIT_EVENT = "git_event"
    AGENT_ACTION = "agent_action"
    IDE_EVENT = "ide_event"
    PORT_CHANGE = "port_change"
    SYSTEM = "system"


# ──────────────────────────────────────────────────────────────────
# Memory Item
# ──────────────────────────────────────────────────────────────────


class MemoryItem(BaseModel):
    """A single memory item at a specific layer and scope.

    Lifecycle:
      L0 RAW → L1 WORKING  (automem, every turn)
      L1 → L2 EPISODIC     (autodream, every N turns)
      L2 → L3 SEMANTIC     (autodream, hourly)
      L3 → L4 CONSOLIDATED (autodream, nightly)
    """

    memory_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    layer: MemoryLayer
    scope_type: MemoryScope
    scope_id: str = Field(default="", description="e.g. 'frontend', 'ruben', 'session-abc'")
    pool: str = Field(default="agent", description="agent | personal | team | domain | topic")
    type: MemoryType
    content: str
    source_event_ids: list[str] = Field(default_factory=list)
    project_id: Optional[str] = None
    topic_ids: list[str] = Field(default_factory=list)
    importance: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    ttl: Optional[str] = None
    embedding: Optional[list[float]] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    @property
    def full_scope(self) -> str:
        if self.scope_type == MemoryScope.GLOBAL_CORE:
            return "global-core"
        return f"{self.scope_type.value}/{self.scope_id}"


# ──────────────────────────────────────────────────────────────────
# Context Protocol — Bidirectional LLM ↔ Memory
# ──────────────────────────────────────────────────────────────────


class ContextRequest(BaseModel):
    """LLM asks memory for relevant context."""

    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str
    query: str
    intent: str = Field(default="answer", description="answer | plan | review | debug | study")
    allowed_scopes: list[str] = Field(default_factory=list)
    token_budget: int = Field(default=8000)
    time_budget_ms: int = Field(default=2000)
    include_raw: bool = False
    priority: str = Field(default="normal", description="low | normal | critical")


class ContextSource(BaseModel):
    """A single source within a context pack."""

    scope: str
    layer: int
    mem_type: str
    score: float
    memory_id: str = ""
    content_preview: str = Field(default="", max_length=500)


class ContextPack(BaseModel):
    """Assembled context ready for injection into LLM window."""

    request_id: str
    query: str = ""
    sources: list[ContextSource] = Field(default_factory=list)
    summary: str = Field(default="", description="Compressed briefing")
    citations: list[str] = Field(default_factory=list)
    omissions: list[str] = Field(default_factory=list)
    token_estimate: int = 0
    reason: str = Field(
        default="llm_request",
        description="llm_request | system_push | periodic_reminder | domain_change",
    )
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_injection_text(self) -> str:
        """Format as text ready for LLM context injection."""
        if not self.sources:
            return "[No relevant context found]"
        parts: list[str] = []
        parts.append(f"=== CONTEXT PACK ({self.reason}) ===")
        parts.append(f"Query: {self.query}")
        parts.append(f"Sources: {len(self.sources)} | Tokens: ~{self.token_estimate}")
        parts.append("")
        parts.append(self.summary)
        parts.append("")
        parts.append(f"Citations: {', '.join(self.citations[:10])}")
        return "\n".join(parts)


class ContextReminder(BaseModel):
    """Proactive context push from memory to LLM."""

    reminder_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    pack: ContextPack
    reason: str = Field(
        default="relevant_to_current_task",
        description="relevant_to_current_task | recent_decision_not_used | domain_change_detected | periodic_reminder | user_mentioned_entity",
    )
    expires_after_turns: int = Field(default=3)
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


# ──────────────────────────────────────────────────────────────────
# Agent Backpack
# ──────────────────────────────────────────────────────────────────


class ScopePolicy(BaseModel):
    """Access policy for a scope in an agent's backpack."""

    scope: str
    read: bool = True
    write: bool = False
    promote: bool = False


class AgentBackpack(BaseModel):
    """An agent's isolated memory backpack with declared scopes."""

    agent_id: str
    role: str = "generalist"
    owner: str = "default"
    home_scope: str = ""
    allowed_scopes: list[str] = Field(default_factory=list)
    default_read_order: list[str] = Field(
        default=["session", "agent", "domain", "team", "personal", "global-core"]
    )
    promotion_policy: str = "default"
    max_context_tokens: int = 8000
    scope_policies: list[ScopePolicy] = Field(default_factory=list)

    @property
    def home_scope_id(self) -> str:
        """Return home_scope as MemoryScope + id."""
        if not self.home_scope:
            return "global-core"
        return self.home_scope


# ──────────────────────────────────────────────────────────────────
# Heartbeat
# ──────────────────────────────────────────────────────────────────


class HeartbeatStatus(BaseModel):
    """Agent heartbeat — the daemon tracks if agent is alive."""

    agent_id: str
    last_seen: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    session_id: str = ""
    turn_count: int = 0
    status: str = Field(default="active", description="active | idle | disconnected")
    last_context_pack_id: str = ""


# ──────────────────────────────────────────────────────────────────
# Raw Event (L0)
# ──────────────────────────────────────────────────────────────────


class RawEvent(BaseModel):
    """L0 raw event — append-only, immutable audit trail."""

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    type: RawEventType
    source: str = Field(description="terminal | ide | filesystem | docker | agent | osquery")
    actor_id: str = "system"
    session_id: str = ""
    scope: str = ""
    attributes: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
