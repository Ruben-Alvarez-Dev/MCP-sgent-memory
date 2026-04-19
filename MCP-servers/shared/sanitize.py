"""Input sanitization and normalization for the MCP Memory Server.

Every entry point (tool handler) MUST pass data through these functions
before it reaches storage, filesystem, or search.

Principles:
  1. Strip dangerous characters early
  2. Normalize unicode/whitespace for consistent search
  3. Validate enums and IDs
  4. Never trust agent input — always sanitize

Usage in any server:
    from shared.sanitize import (
        sanitize_text, sanitize_filename, sanitize_folder,
        sanitize_tags, sanitize_user_id, validate_json_field,
        normalize_query, SanitizeError,
    )
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any


class SanitizeError(ValueError):
    """Raised when input cannot be safely sanitized."""
    pass


# ── Constants ──────────────────────────────────────────────────────

# Maximum lengths to prevent abuse
MAX_TEXT_LENGTH = 100_000       # ~25K tokens
MAX_TITLE_LENGTH = 500
MAX_FILENAME_LENGTH = 200
MAX_TAG_LENGTH = 100
MAX_USER_ID_LENGTH = 128
MAX_TAGS_COUNT = 20

# Valid event types for automem ingest
VALID_EVENT_TYPES = frozenset({
    "terminal", "git", "file", "system",
    "diff_proposed", "diff_accepted", "diff_rejected", "diff_applied", "diff_failed",
})

# Valid memory types
VALID_MEM_TYPES = frozenset({
    "step", "fact", "preference", "episode", "conversation",
    "bug_fix", "config", "code_snippet", "error_trace", "decision", "summary",
})

# Valid scopes
VALID_SCOPES = frozenset({
    "session", "agent", "personal", "domain", "project", "global-core",
})

# Valid vault folders (whitelist)
SAFE_VAULT_FOLDERS = frozenset({
    "Inbox", "Decisiones", "Conocimiento", "Episodios",
    "Entidades", "Personas", "Log_Global", "Templates", "Notes",
})

# Characters forbidden in filenames (Windows + macOS + Linux)
_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Null bytes and control characters (except newline, tab)
_CONTROL_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')

# Path traversal patterns
_TRAVERSAL_RE = re.compile(r'\.\.|\.\//|\\\\')


# ── Text sanitization ──────────────────────────────────────────────

def sanitize_text(text: str, *, max_length: int = MAX_TEXT_LENGTH, field: str = "content") -> str:
    """Sanitize free-form text content.

    - Strips null bytes and control characters (keeps \\n and \\t)
    - Normalizes unicode (NFC)
    - Strips leading/trailing whitespace
    - Collapses multiple spaces/newlines
    - Enforces max length
    """
    if not isinstance(text, str):
        raise SanitizeError(f"{field} must be a string, got {type(text).__name__}")

    if not text.strip():
        raise SanitizeError(f"{field} cannot be empty or whitespace-only")

    # Remove null bytes and control chars (keep \n \t)
    cleaned = _CONTROL_RE.sub('', text)

    # Normalize unicode to composed form (é → é, not e + combining accent)
    cleaned = unicodedata.normalize('NFC', cleaned)

    # Strip leading/trailing whitespace
    cleaned = cleaned.strip()

    # Collapse 3+ consecutive newlines to 2
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)

    # Collapse 3+ consecutive spaces to 1 (but preserve indentation)
    cleaned = re.sub(r' {3,}', ' ', cleaned)

    if len(cleaned) > max_length:
        raise SanitizeError(
            f"{field} too long: {len(cleaned)} chars (max {max_length})"
        )

    return cleaned


def normalize_query(query: str) -> str:
    """Normalize a search query for consistent embedding/search.

    Same as sanitize_text but:
    - Replaces newlines with spaces (queries are single-line)
    - Lower maximum length (queries should be concise)
    """
    if not isinstance(query, str):
        raise SanitizeError("query must be a string")

    cleaned = _CONTROL_RE.sub('', query)
    cleaned = unicodedata.normalize('NFC', cleaned)
    cleaned = cleaned.replace('\n', ' ').replace('\r', ' ')
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    if not cleaned:
        raise SanitizeError("query cannot be empty")

    if len(cleaned) > 2000:
        cleaned = cleaned[:2000]

    return cleaned


# ── Filename sanitization ──────────────────────────────────────────

def sanitize_filename(filename: str, *, field: str = "filename") -> str:
    """Sanitize a filename for safe filesystem use.

    - Removes path separators and traversal patterns
    - Removes characters invalid on any OS
    - Replaces spaces with hyphens
    - Enforces max length
    - Ensures non-empty result
    """
    if not isinstance(filename, str):
        raise SanitizeError(f"{field} must be a string")

    # Remove any path components (take basename only)
    filename = os.path.basename(filename)

    # Remove extension if present (we add it later)
    filename = Path(filename).stem

    # Strip path traversal
    if _TRAVERSAL_RE.search(filename):
        raise SanitizeError(f"{field} contains path traversal characters")

    # Remove invalid chars
    filename = _FILENAME_RE.sub('', filename)

    # Replace spaces with hyphens
    filename = filename.replace(' ', '-')

    # Collapse multiple hyphens
    filename = re.sub(r'-{2,}', '-', filename)

    # Remove leading/trailing hyphens and dots
    filename = filename.strip('-.')

    # Normalize unicode
    filename = unicodedata.normalize('NFC', filename)

    if not filename:
        raise SanitizeError(f"{field} is empty after sanitization")

    if len(filename) > MAX_FILENAME_LENGTH:
        filename = filename[:MAX_FILENAME_LENGTH]

    return filename


def sanitize_folder(folder: str, *, allowed: frozenset[str] | None = None) -> str:
    """Validate a folder name against a whitelist.

    - Only allows pre-approved folder names
    - Prevents path traversal
    - Falls back to default if folder is empty
    """
    if not isinstance(folder, str):
        raise SanitizeError("folder must be a string")

    # Strip and normalize
    folder = folder.strip()

    if not folder:
        return "Inbox"  # Safe default

    # Check for path traversal
    if '/' in folder or '\\' in folder or '..' in folder:
        raise SanitizeError(f"Invalid folder: path separators not allowed")

    # Whitelist check
    whitelist = allowed or SAFE_VAULT_FOLDERS
    if folder not in whitelist:
        raise SanitizeError(
            f"Invalid folder '{folder}'. Allowed: {', '.join(sorted(whitelist))}"
        )

    return folder


# ── Structured field sanitization ──────────────────────────────────

def sanitize_tags(tags: str) -> list[str]:
    """Parse and sanitize a comma-separated tags string.

    - Splits by comma
    - Strips whitespace, lowercases
    - Removes empty and duplicate tags
    - Enforces max count and length per tag
    - Removes special characters from tags
    """
    if not isinstance(tags, str):
        return []

    raw_tags = [t.strip().lower() for t in tags.split(',') if t.strip()]

    # Remove special chars from each tag (keep letters, numbers, hyphens, unicode)
    clean_tags = []
    seen = set()
    for tag in raw_tags:
        # Keep only word chars, hyphens, and unicode letters
        tag = re.sub(r'[^\w\s-]', '', tag, flags=re.UNICODE)
        tag = tag.replace(' ', '-')
        tag = tag.strip('-.')

        if not tag or len(tag) > MAX_TAG_LENGTH:
            continue
        if tag not in seen:
            seen.add(tag)
            clean_tags.append(tag)

    if len(clean_tags) > MAX_TAGS_COUNT:
        clean_tags = clean_tags[:MAX_TAGS_COUNT]

    return clean_tags


def sanitize_user_id(user_id: str) -> str:
    """Sanitize a user identifier.

    - Strips whitespace
    - Lowercases
    - Removes special characters (keep alphanumeric, hyphens, underscores)
    - Enforces max length
    """
    if not isinstance(user_id, str):
        raise SanitizeError("user_id must be a string")

    cleaned = user_id.strip().lower()
    cleaned = re.sub(r'[^a-z0-9_-]', '', cleaned)

    if not cleaned:
        raise SanitizeError("user_id cannot be empty")

    if len(cleaned) > MAX_USER_ID_LENGTH:
        cleaned = cleaned[:MAX_USER_ID_LENGTH]

    return cleaned


def validate_enum(value: str, valid: frozenset[str], field: str = "value") -> str:
    """Validate that a value is in the allowed set.

    Returns the validated value or raises SanitizeError.
    """
    if not isinstance(value, str):
        raise SanitizeError(f"{field} must be a string")

    value = value.strip().lower()

    if value not in valid:
        raise SanitizeError(
            f"Invalid {field}: '{value}'. Allowed: {', '.join(sorted(valid))}"
        )

    return value


def validate_json_field(json_str: str, field: str = "json") -> Any:
    """Parse and validate a JSON string field.

    - Ensures valid JSON
    - Prevents excessively deep nesting
    - Returns parsed object
    """
    if not isinstance(json_str, str):
        raise SanitizeError(f"{field} must be a string")

    json_str = json_str.strip()
    if not json_str:
        raise SanitizeError(f"{field} cannot be empty")

    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise SanitizeError(f"Invalid JSON in {field}: {e}")

    # Prevent deep nesting (DoS vector)
    depth = _json_depth(parsed)
    if depth > 10:
        raise SanitizeError(f"{field} nesting too deep: {depth} levels (max 10)")

    # Prevent oversized JSON
    size = len(json.dumps(parsed))
    if size > MAX_TEXT_LENGTH:
        raise SanitizeError(f"{field} too large: {size} bytes (max {MAX_TEXT_LENGTH})")

    return parsed


def _json_depth(obj: Any, depth: int = 0) -> int:
    """Measure maximum nesting depth of a JSON structure."""
    if isinstance(obj, dict):
        if not obj:
            return depth + 1
        return max(_json_depth(v, depth + 1) for v in obj.values())
    elif isinstance(obj, list):
        if not obj:
            return depth + 1
        return max(_json_depth(v, depth + 1) for v in obj)
    return depth


# ── Composite validators for common patterns ───────────────────────

def validate_memorize(content: str, mem_type: str, scope: str, tags: str) -> dict:
    """Validate all inputs for automem.memorize. Returns cleaned values."""
    return {
        "content": sanitize_text(content, field="content"),
        "mem_type": validate_enum(mem_type, VALID_MEM_TYPES, "mem_type"),
        "scope": validate_enum(scope, VALID_SCOPES, "scope"),
        "tags": sanitize_tags(tags),
    }


def validate_ingest_event(event_type: str, source: str, content: str) -> dict:
    """Validate all inputs for automem.ingest_event. Returns cleaned values."""
    return {
        "event_type": validate_enum(event_type, VALID_EVENT_TYPES, "event_type"),
        "source": sanitize_text(source, max_length=200, field="source"),
        "content": sanitize_text(content, max_length=MAX_TEXT_LENGTH, field="content"),
    }


def validate_save_decision(title: str, content: str, category: str, tags: str, scope: str) -> dict:
    """Validate all inputs for engram.save_decision. Returns cleaned values."""
    return {
        "title": sanitize_text(title, max_length=MAX_TITLE_LENGTH, field="title"),
        "content": sanitize_text(content, field="content"),
        "category": sanitize_filename(category, field="category"),
        "tags": sanitize_tags(tags),
        "scope": sanitize_filename(scope, field="scope"),
    }


def validate_vault_write(folder: str, filename: str, content: str, tags: str) -> dict:
    """Validate all inputs for engram.vault_write. Returns cleaned values."""
    return {
        "folder": sanitize_folder(folder),
        "filename": sanitize_filename(filename),
        "content": sanitize_text(content, field="content"),
        "tags": sanitize_tags(tags),
    }


def validate_add_memory(content: str, user_id: str) -> dict:
    """Validate all inputs for mem0.add_memory. Returns cleaned values."""
    return {
        "content": sanitize_text(content, field="content"),
        "user_id": sanitize_user_id(user_id),
    }


def validate_request_context(query: str, intent: str) -> dict:
    """Validate all inputs for vk-cache.request_context. Returns cleaned values."""
    valid_intents = frozenset({"answer", "plan", "review", "debug", "study"})
    return {
        "query": normalize_query(query),
        "intent": validate_enum(intent, valid_intents, "intent"),
    }


def validate_push_reminder(query: str, agent_id: str) -> dict:
    """Validate all inputs for vk-cache.push_reminder. Returns cleaned values."""
    return {
        "query": sanitize_text(query, max_length=2000, field="query"),
        "agent_id": sanitize_user_id(agent_id),
    }
