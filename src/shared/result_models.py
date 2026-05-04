"""Pydantic return models for all MCP tool responses.

Replaces raw JSON string returns with typed, schema-generating models.
FastMCP serializes these automatically as MCP structured output.
"""

from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


# ── L0_capture ───────────────────────────────────────────────────────

class MemorizeResult(BaseModel):
    status: str = "stored"
    memory_id: str
    layer: str
    scope: str

class IngestResult(BaseModel):
    status: str = "ingested"
    event_id: str
    layer: str

class HeartbeatResult(BaseModel):
    status: str = "active"
    agent_id: str
    turn_count: int
    promotion_due: bool = False
    message: str = ""

class L0CaptureStatusResult(BaseModel):
    daemon: str = "L0_capture"
    status: str = "RUNNING"
    qdrant: str = "OK"
    llama_cpp: str = "OK"
    L0_events_jsonl: int = 0
    stored_memories: int = 0
    staged_change_sets: int = 0


# ── autodream ──────────────────────────────────────────────────────

class ConsolidateResult(BaseModel):
    status: str = "consolidation complete"
    forced: bool = False
    results: list[str] = Field(default_factory=list)

class DreamResult(BaseModel):
    status: str
    total_dreams: int = 0

class LayerResult(BaseModel):
    layer: str
    count: int
    memories: list[dict[str, Any]] = Field(default_factory=list)

class AutoDreamStatusResult(BaseModel):
    daemon: str = "AutoDream"
    status: str = "RUNNING"
    state: dict[str, Any] = Field(default_factory=dict)


# ── vk-cache ───────────────────────────────────────────────────────

class ContextPackResult(BaseModel):
    context_pack: dict[str, Any] = Field(default_factory=dict)
    injection_text: str = ""

class ReminderListResult(BaseModel):
    agent_id: str
    reminders: list[dict[str, Any]] = Field(default_factory=list)
    count: int = 0

class ReminderPushResult(BaseModel):
    status: str = "reminder_pushed"
    reminder_id: str
    sources: int = 0

class DismissResult(BaseModel):
    status: str
    reminder_id: str = ""

class ContextShiftResult(BaseModel):
    shift_detected: bool
    similarity: float = 0.0
    new_context: str = ""

class VkCacheStatusResult(BaseModel):
    daemon: str = "L5_routing"
    status: str = "RUNNING"
    qdrant: str = "OK"
    active_reminders: int = 0


# ── conversation-store ─────────────────────────────────────────────

class SaveConversationResult(BaseModel):
    status: str = "saved"
    thread_id: str

class SearchResult(BaseModel):
    count: int
    results: list[dict[str, Any]] = Field(default_factory=list)

class ThreadListResult(BaseModel):
    count: int
    threads: list[dict[str, Any]] = Field(default_factory=list)

class ConversationStatusResult(BaseModel):
    daemon: str = "L2_conversations"
    status: str = "RUNNING"
    threads: int = 0


# ── L3_facts ───────────────────────────────────────────────────────

class AddMemoryResult(BaseModel):
    status: str = "added"
    memory_id: str

class L3FactsStatusResult(BaseModel):
    daemon: str = "L3_facts"
    status: str = "RUNNING"
    memories: int = 0


# ── L3_decisions ───────────────────────────────────────────────────

class SaveDecisionResult(BaseModel):
    status: str = "saved"
    file_path: str
    title: str

class DecisionListResult(BaseModel):
    count: int
    decisions: list[dict[str, Any]] = Field(default_factory=list)

class VaultWriteResult(BaseModel):
    status: str = "written"
    path: str

class VaultIntegrityResult(BaseModel):
    status: str = "ok"
    total_notes: int = 0

class VaultNotesResult(BaseModel):
    count: int
    notes: list[dict[str, str]] = Field(default_factory=list)

class ModelPackResult(BaseModel):
    name: str
    content: str = ""
    status: str = ""

class ModelPackListResult(BaseModel):
    packs: list[str] = Field(default_factory=list)

class L3DecisionsStatusResult(BaseModel):
    daemon: str = "L3_decisions"
    status: str = "RUNNING"
    decision_files: int = 0
    vault_notes: int = 0


# ── sequential-thinking ────────────────────────────────────────────

class ThinkingResult(BaseModel):
    session_id: str
    steps: int
    summary: str = ""
    thoughts: list[dict[str, Any]] = Field(default_factory=list)

class PlanResult(BaseModel):
    status: str = "created"
    plan_id: str
    steps: int = 0

class PlanUpdateResult(BaseModel):
    status: str = "updated"
    plan_id: str = ""
    step: int = 0

class ReflectResult(BaseModel):
    status: str = "reflected"
    session_id: str
    steps: int
    summary: str = ""

class SessionResult(BaseModel):
    session_id: str
    steps: int
    thoughts: list[dict[str, Any]] = Field(default_factory=list)

class SessionListResult(BaseModel):
    count: int
    sessions: list[str] = Field(default_factory=list)

class ChangeSetResult(BaseModel):
    status: str = "proposed"
    change_set_id: str
    changes: int = 0

class SequentialThinkingStatusResult(BaseModel):
    daemon: str = "Lx_reasoning"
    status: str = "RUNNING"
    sessions: int = 0
    plans: int = 0
    staged: int = 0
