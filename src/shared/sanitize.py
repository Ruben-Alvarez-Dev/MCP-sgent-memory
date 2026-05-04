"""Input sanitization and normalization for the MCP Memory Server.

Every entry point (tool handler) MUST pass data through these functions
before it reaches storage, filesystem, or search.

Based on:
  - OWASP Input Validation Cheat Sheet
  - Unicode Technical Report #36 (Security Considerations)
  - Unicode Technical Standard #39 (Security Mechanisms)
  - W3C String Management best practices
  - IETF RFC 3986 (URI — path segment rules for filenames)

Principles:
  1. Strip dangerous characters early — all invisible/control chars
  2. Normalize unicode (NFKC for identifiers, NFC for text)
  3. Normalize all whitespace variants to standard space/newline
  4. Validate enums and IDs against whitelists
  5. Enforce length limits to prevent resource exhaustion
  6. Never trust agent input — always sanitize, even from "trusted" agents

Usage in any server:
    from shared.sanitize import (
        sanitize_text, sanitize_code, sanitize_filename, sanitize_folder,
        sanitize_tags, sanitize_user_id, validate_json_field,
        normalize_query, SanitizeError,
    )
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Any


class SanitizeError(ValueError):
    """Raised when input cannot be safely sanitized."""
    pass


# ── Constants ──────────────────────────────────────────────────────

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
    "tool_call", "user_prompt", "file_edited",
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

# Valid vault folders (whitelist — only these directories)
SAFE_VAULT_FOLDERS = frozenset({
    "inbox", "decisions", "knowledge", "episodes",
    "entities", "people", "log_global", "templates", "notes",
    "Decisions", "Knowledge", "Episodes", "Entities", "People",
    "Patterns", "Learnings", "Projects", "Sandbox", "Archive",
    "Patrones", "Aprendizajes", "Proyectos", "Archivos",
})

# Windows reserved filenames (case-insensitive)
# https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file
_WINDOWS_RESERVED = frozenset({
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
})

# Characters forbidden in filenames across all OS
# Windows: < > : " / \\ | ? *
# macOS: :
# Linux: / \0
# All: control chars 0x00-0x1F
_FILENAME_FORBIDDEN_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# All control characters (C0 + C1 + DEL) — KEEP \t \n as significant whitespace
_CONTROL_CHARS_RE = re.compile(
    r'[\x00-\x08'   # C0: NUL through BS (keep TAB=0x09)
    r'\x0b\x0c'     # C0: VT, FF (keep LF=0x0A, CR handled separately)
    r'\x0e-\x1f'    # C0: SO through US
    r'\x7f'         # DEL
    r'\x80-\x9f]'   # C1 control characters
)

# Invisible and formatting Unicode characters that should be stripped
# Based on UTS #39 and W3C recommendations
# Includes: Zero-width spaces/joiners, BOM, soft hyphen, word joiner,
# variation selectors, interlinear annotations, etc.
_INVISIBLE_CHARS_RE = re.compile(
    '['
    r'\u034F'        # COMBINING GRAPHEME JOINER
    r'\u061C'        # ARABIC LETTER MARK
    r'\u115F\u1160'  # HANGUL CHOSEONG/FILLER
    r'\u17B4\u17B5'  # KHMER VOWEL INHERENT AQ/AA
    r'\u180B-\u180F' # MONGOLIAN FREE VARIATION SELECTORS
    r'\u200B-\u200F' # ZERO WIDTH SPACE, NON-BREAKING, EN/HAIR SPACE, LRM, RLM
    r'\u2028-\u202E' # LINE/PARA SEPARATOR, LRE/RLE/PDF/LRO/RLO
    r'\u2060-\u206F' # WORD JOINER through NOMINAL DIGIT SHAPES
    r'\u3164'        # HANGUL FILLER
    r'\uFE00-\uFE0F' # VARIATION SELECTORS 1-16
    r'\uFEFF'        # BOM / ZERO WIDTH NO-BREAK SPACE
    r'\uFFA0'        # HALFWIDTH HANGUL FILLER
    r'\uFFF0-\uFFF8' # Unassigned interlinear annotations
    r'\U00013430-\U0001343F' # EGYPTIAN HIEROGLYPH FORMAT CONTROLS
    r'\U0001BCA0-\U0001BCA3' # SHORTHAND FORMAT CONTROLS
    r'\U0001D173-\U0001D17A' # MUSICAL SYMBOL BEAMED GROUPS
    r'\U000E0000-\U000E0FFF' # TAG characters (used for emoji tags, spoofing)
    ']'
)

# All Unicode whitespace variants — normalize to regular space
# Based on Unicode Property: White_Space=Yes
# Excludes: \t (tab), \n (newline), \r (carriage return) — handled separately
_WHITESPACE_RE = re.compile(
    '['
    r'\u00A0'        # NO-BREAK SPACE (NBSP)
    r'\u1680'        # OGHAM SPACE MARK
    r'\u2000-\u200A' # EN QUAD through HAIR SPACE
    r'\u2028'        # LINE SEPARATOR
    r'\u2029'        # PARAGRAPH SEPARATOR
    r'\u202F'        # NARROW NO-BREAK SPACE
    r'\u205F'        # MEDIUM MATHEMATICAL SPACE
    r'\u3000'        # IDEOGRAPHIC SPACE
    ']'
)

# Bi-directional override characters (CVE-2021-42574)
# These can make text appear different than its logical content
_BIDI_RE = re.compile(
    '['
    r'\u200E'        # LEFT-TO-RIGHT MARK
    r'\u200F'        # RIGHT-TO-LEFT MARK
    r'\u202A'        # LEFT-TO-RIGHT EMBEDDING
    r'\u202B'        # RIGHT-TO-LEFT EMBEDDING
    r'\u202C'        # POP DIRECTIONAL FORMATTING
    r'\u202D'        # LEFT-TO-RIGHT OVERRIDE
    r'\u202E'        # RIGHT-TO-LEFT OVERRIDE
    r'\u2066'        # LEFT-TO-RIGHT ISOLATE
    r'\u2067'        # RIGHT-TO-LEFT ISOLATE
    r'\u2068'        # FIRST STRONG ISOLATE
    r'\u2069'        # POP DIRECTIONAL ISOLATE
    ']'
)


# ── Core sanitization functions ────────────────────────────────────

def _strip_control_chars(text: str) -> str:
    """Remove C0/C1 control characters except tab and newline."""
    text = _CONTROL_CHARS_RE.sub('', text)
    # Also strip individual CR (\r) — normalize \r\n to \n
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    return text


def _strip_invisible_chars(text: str) -> str:
    """Remove zero-width spaces, BOM, variation selectors, and other invisible Unicode.
    
    Soft hyphen (U+00AD) is replaced with a hyphen, not stripped — it has
    semantic meaning (line break opportunity). All others are removed.
    """
    # Soft hyphen → regular hyphen (it means "possible line break")
    text = text.replace('\u00AD', '-')
    # Build invisible set from codepoint ranges (avoids \\U regex bugs)
    invisible = set()
    for start, end in [
        (0x034F, 0x034F),   # COMBINING GRAPHEME JOINER
        (0x061C, 0x061C),   # ARABIC LETTER MARK
        (0x115F, 0x1160),   # HANGUL FILLER
        (0x17B4, 0x17B5),   # KHMER VOWEL INHERENT
        (0x180B, 0x180F),   # MONGOLIAN VARIATION SELECTORS
        (0x200B, 0x200F),   # ZERO WIDTH, LRM, RLM
        (0x2028, 0x202E),   # LINE/PARA SEP, directional overrides
        (0x2060, 0x206F),   # WORD JOINER etc
        (0x3164, 0x3164),   # HANGUL FILLER
        (0xFE00, 0xFE0F),   # VARIATION SELECTORS 1-16
        (0xFEFF, 0xFEFF),   # BOM
        (0xFFA0, 0xFFA0),   # HALFWIDTH HANGUL FILLER
        (0xFFF0, 0xFFF8),   # Interlinear annotations
        (0x13430, 0x1343F), # EGYPTIAN HIEROGLYPH
        (0x1BCA0, 0x1BCA3), # SHORTHAND FORMAT
        (0x1D173, 0x1D17A), # MUSICAL SYMBOLS
        (0xE0000, 0xE0FFF), # TAG characters
    ]:
        for cp in range(start, end + 1):
            invisible.add(chr(cp))
    return ''.join(c for c in text if c not in invisible)


def _strip_bidi_overrides(text: str) -> str:
    """Remove bi-directional text override characters (CVE-2021-42574)."""
    return _BIDI_RE.sub('', text)


def _normalize_whitespace(text: str) -> str:
    """Normalize all Unicode whitespace variants to regular space/newline."""
    # Replace whitespace variants with regular space
    text = _WHITESPACE_RE.sub(' ', text)
    # Tab → space (queries don't need tabs)
    text = text.replace('\t', ' ')
    # Collapse multiple spaces to one
    text = re.sub(r' {2,}', ' ', text)
    return text


# ── Text sanitization ──────────────────────────────────────────────

def _strip_html_tags(text: str) -> str:
    """Remove HTML/XML tags to prevent XSS and markup injection.

    Strips all <tag>...</tag> constructs including self-closing <tag/>.
    Also strips HTML entities (&lt; &amp; etc.) back to literal characters
    since memories store plain text, not rendered HTML.

    Preserves: content between tags, angle brackets in code/math contexts
    Strategy: remove anything that looks like an HTML tag, keep the rest.
    """
    # 1. Remove script/style blocks entirely (content + tags)
    #    <script>...</script> — content is executable, never safe to keep
    #    <style>...</style> — content is CSS, not user-visible text
    cleaned = re.sub(r'<\s*script[^>]*>.*?<\s*/\s*script\s*>', '', text, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r'<\s*style[^>]*>.*?<\s*/\s*style\s*>', '', cleaned, flags=re.IGNORECASE | re.DOTALL)

    # 2. Remove all remaining HTML/XML tags (including self-closing)
    cleaned = re.sub(r'<\s*/?\s*[a-zA-Z][a-zA-Z0-9]*(?:\s[^>]*)?/?>', '', cleaned)

    # 3. Decode common HTML entities to plain text
    #    (&lt; → <, &amp; → &, &quot; → ", etc.)
    html_entities = {
        '&lt;': '<', '&gt;': '>', '&amp;': '&', '&quot;': '"',
        '&#39;': "'", '&apos;': "'", '&nbsp;': ' ',
    }
    for entity, char in html_entities.items():
        cleaned = cleaned.replace(entity, char)

    # 4. Decode numeric entities (&#60; → <, &#x3C; → <)
    cleaned = re.sub(r'&#(\d+);', lambda m: chr(int(m.group(1))) if int(m.group(1)) < 0x110000 else '', cleaned)
    cleaned = re.sub(r'&#x([0-9a-fA-F]+);', lambda m: chr(int(m.group(1), 16)) if int(m.group(1), 16) < 0x110000 else '', cleaned)

    return cleaned


def sanitize_text(text: str, *, max_length: int = MAX_TEXT_LENGTH, field: str = "content") -> str:
    """Sanitize free-form text content (memories, decisions, events).

    Pipeline: type check → HTML strip → control chars → invisible chars →
              bidi → unicode normalize → whitespace → length check

    Preserves: newlines (logical structure), tabs (code), unicode letters/emoji
    Removes: HTML tags, null bytes, control chars, zero-width chars, BOM, bidi overrides
    Normalizes: unicode NFC, whitespace variants → regular space
    """
    if not isinstance(text, str):
        raise SanitizeError(f"{field} must be a string, got {type(text).__name__}")

    # 1. Strip HTML/XML tags (prevent XSS)
    cleaned = _strip_html_tags(text)

    # 2. Strip control characters (keep \n and \t)
    cleaned = _strip_control_chars(cleaned)

    # 3. Strip invisible/formatting Unicode
    cleaned = _strip_invisible_chars(cleaned)

    # 4. Strip bi-directional overrides
    cleaned = _strip_bidi_overrides(cleaned)

    # 5. Normalize unicode to composed form
    #    NFC: preferred for text storage (é → single codepoint)
    cleaned = unicodedata.normalize('NFC', cleaned)

    # 6. Normalize whitespace variants to standard space
    cleaned = _normalize_whitespace(cleaned)

    # 7. Strip leading/trailing whitespace
    cleaned = cleaned.strip()

    # 8. Collapse 3+ consecutive newlines to 2
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)

    if not cleaned:
        raise SanitizeError(f"{field} cannot be empty or whitespace-only")

    if len(cleaned) > max_length:
        raise SanitizeError(
            f"{field} too long: {len(cleaned)} chars (max {max_length})"
        )

    return cleaned


def sanitize_code(text: str, *, max_length: int = MAX_TEXT_LENGTH, field: str = "code") -> str:
    """Sanitize source code content.

    Same as sanitize_text but preserves tabs (significant in Python/Makefile)
    and does NOT normalize whitespace (indentation matters).
    Does NOT strip HTML — code may contain HTML/XML templates.
    """
    if not isinstance(text, str):
        raise SanitizeError(f"{field} must be a string, got {type(text).__name__}")

    # Strip null bytes and control chars (keep \n \t)
    cleaned = _strip_control_chars(text)
    # Strip invisible Unicode (ZWS, BOM, etc.)
    cleaned = _strip_invisible_chars(cleaned)
    # Strip bidi overrides
    cleaned = _strip_bidi_overrides(cleaned)
    # NFC normalize
    cleaned = unicodedata.normalize('NFC', cleaned)
    # DO NOT normalize whitespace — indentation matters
    # DO NOT strip HTML — code may contain HTML/XML templates
    # Strip leading/trailing
    cleaned = cleaned.strip()

    if not cleaned:
        raise SanitizeError(f"{field} cannot be empty")

    if len(cleaned) > max_length:
        raise SanitizeError(f"{field} too long: {len(cleaned)} chars (max {max_length})")

    return cleaned


def normalize_query(query: str) -> str:
    """Normalize a search query for consistent embedding/search.

    Same pipeline as sanitize_text plus:
    - HTML strip (queries may come from web content)
    - Newlines → spaces (queries are single-line)
    - Shorter max length
    - NFKC normalization (fullwidth digits → ASCII, ligatures → parts)
    """
    if not isinstance(query, str):
        raise SanitizeError("query must be a string")

    cleaned = _strip_html_tags(query)
    cleaned = _strip_control_chars(cleaned)
    cleaned = _strip_invisible_chars(cleaned)
    cleaned = _strip_bidi_overrides(cleaned)

    # NFKC: more aggressive normalization for search
    # Fullwidth ９ → 9, ligature ﬁ → fi, etc.
    cleaned = unicodedata.normalize('NFKC', cleaned)

    # All whitespace → single space (queries are single-line)
    cleaned = cleaned.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
    cleaned = _normalize_whitespace(cleaned)
    cleaned = cleaned.strip()

    if not cleaned:
        raise SanitizeError("query cannot be empty")

    if len(cleaned) > 2000:
        cleaned = cleaned[:2000]

    return cleaned


# ── Filename sanitization ──────────────────────────────────────────

def sanitize_filename(filename: str, *, field: str = "filename") -> str:
    """Sanitize a filename for safe filesystem use.

    Pipeline: basename → strip traversal → remove invalid chars →
              replace spaces → collapse hyphens → length check →
              reserved name check

    Based on: OWASP Path Traversal prevention, RFC 3986 unreserved chars
    """
    if not isinstance(filename, str):
        raise SanitizeError(f"{field} must be a string")

    # 1. Take basename only (strips any path component)
    filename = os.path.basename(filename)

    # 2. Remove extension if present (caller adds it)
    filename = Path(filename).stem

    # 3. Strip null bytes
    filename = filename.replace('\x00', '')

    # 4. Reject path traversal
    if '..' in filename:
        raise SanitizeError(f"{field} contains path traversal (..)")

    # 5. Remove OS-forbidden characters
    filename = _FILENAME_FORBIDDEN_RE.sub('', filename)

    # 6. Replace spaces with hyphens
    filename = filename.replace(' ', '-')

    # 7. Collapse multiple hyphens/underscores
    filename = re.sub(r'[-_]{2,}', '-', filename)

    # 8. Strip leading/trailing hyphens and dots (hidden files, relative refs)
    filename = filename.strip('-.')

    # 9. NFC normalize
    filename = unicodedata.normalize('NFC', filename)

    # 10. Non-empty check
    if not filename:
        raise SanitizeError(f"{field} is empty after sanitization")

    # 11. Length limit
    if len(filename) > MAX_FILENAME_LENGTH:
        filename = filename[:MAX_FILENAME_LENGTH]

    # 12. Windows reserved name check (case-insensitive)
    stem_upper = filename.upper().split('.')[0]  # handle "CON.txt" etc
    if stem_upper in _WINDOWS_RESERVED:
        raise SanitizeError(
            f"{field} is a reserved system name: '{stem_upper}'"
        )

    return filename


def sanitize_folder(folder: str, *, allowed: frozenset[str] | None = None) -> str:
    """Validate a folder name against a whitelist.

    - Only allows pre-approved folder names (no arbitrary paths)
    - Prevents path traversal
    - Falls back to default if empty
    """
    if not isinstance(folder, str):
        raise SanitizeError("folder must be a string")

    folder = folder.strip()

    if not folder:
        return "inbox"

    # Reject any path component
    if '/' in folder or '\\' in folder or '..' in folder or '\x00' in folder:
        raise SanitizeError("Invalid folder: path separators not allowed")

    # Whitelist check
    whitelist = allowed or SAFE_VAULT_FOLDERS
    if folder not in whitelist:
        raise SanitizeError(
            f"Invalid folder '{folder}'. Allowed: {', '.join(sorted(whitelist))}"
        )

    return folder


# ── Identifier sanitization ────────────────────────────────────────

def sanitize_user_id(user_id: str) -> str:
    """Sanitize a user/agent identifier.

    Pipeline: strip → lowercase → NFKC normalize → keep [a-z0-9_-] → length check
    NFKC because identifiers should normalize fullwidth chars and ligatures.
    """
    if not isinstance(user_id, str):
        raise SanitizeError("user_id must be a string")

    cleaned = user_id.strip()

    # NFKC: fullwidth chars → ASCII, ligatures → parts
    cleaned = unicodedata.normalize('NFKC', cleaned)

    # Lowercase
    cleaned = cleaned.lower()

    # Keep only safe chars
    cleaned = re.sub(r'[^a-z0-9_-]', '', cleaned)

    if not cleaned:
        raise SanitizeError("user_id cannot be empty after sanitization")

    if len(cleaned) > MAX_USER_ID_LENGTH:
        cleaned = cleaned[:MAX_USER_ID_LENGTH]

    return cleaned


def sanitize_thread_id(thread_id: str) -> str:
    """Sanitize a thread/session identifier.

    Less restrictive than user_id — allows dots and forward slashes
    for hierarchical identifiers like "project/session-abc".
    """
    if not isinstance(thread_id, str):
        raise SanitizeError("thread_id must be a string")

    cleaned = thread_id.strip()
    cleaned = unicodedata.normalize('NFKC', cleaned)
    # Remove null bytes and control chars
    cleaned = _strip_control_chars(cleaned)
    cleaned = _strip_invisible_chars(cleaned)

    if not cleaned:
        raise SanitizeError("thread_id cannot be empty")

    # Block path traversal
    if '..' in cleaned:
        raise SanitizeError("thread_id contains path traversal (..)")

    if len(cleaned) > 256:
        cleaned = cleaned[:256]

    return cleaned


# ── Structured field sanitization ──────────────────────────────────

def sanitize_tags(tags: str) -> list[str]:
    """Parse and sanitize comma-separated tags.

    Pipeline: split by comma → strip → lowercase → NFKC →
              remove special chars → deduplicate → length/count limits
    """
    if not isinstance(tags, str):
        return []

    raw_tags = [t.strip() for t in tags.split(',') if t.strip()]

    clean_tags = []
    seen = set()
    for tag in raw_tags:
        # NFKC for consistent comparison
        tag = unicodedata.normalize('NFKC', tag)
        tag = tag.lower()
        # Keep only word chars, hyphens, unicode letters
        tag = re.sub(r'[^\w-]', '', tag, flags=re.UNICODE)
        tag = tag.strip('-.')

        if not tag or len(tag) > MAX_TAG_LENGTH:
            continue
        if tag not in seen:
            seen.add(tag)
            clean_tags.append(tag)

    return clean_tags[:MAX_TAGS_COUNT]


def validate_enum(value: str, valid: frozenset[str], field: str = "value") -> str:
    """Validate that a value is in the allowed set."""
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

    Pipeline: parse JSON → depth check → size check
    Prevents: JSON bombs (deep nesting), oversized payloads
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

    # Prevent deep nesting (JSON bomb)
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
        return max(_json_depth(v, depth + 1) for v in obj.values()) if obj else depth + 1
    elif isinstance(obj, list):
        return max(_json_depth(v, depth + 1) for v in obj) if obj else depth + 1
    return depth


# ── Composite validators for tool handlers ────────────────────────

def validate_memorize(content: str, mem_type: str, scope: str, tags: str) -> dict:
    """Validate all inputs for L3_decisions.save_decision."""
    return {
        "content": sanitize_text(content, field="content"),
        "mem_type": validate_enum(mem_type, VALID_MEM_TYPES, "mem_type"),
        "scope": validate_enum(scope, VALID_SCOPES, "scope"),
        "tags": sanitize_tags(tags),
    }


def validate_ingest_event(event_type: str, source: str, content: str) -> dict:
    """Validate all inputs for L0_capture.ingest_event."""
    return {
        "event_type": validate_enum(event_type, VALID_EVENT_TYPES, "event_type"),
        "source": sanitize_text(source, max_length=200, field="source"),
        "content": sanitize_text(content, max_length=MAX_TEXT_LENGTH, field="content"),
    }


def validate_save_decision(title: str, content: str, category: str, tags: str, scope: str) -> dict:
    """Validate all inputs for engram.save_decision."""
    return {
        "title": sanitize_text(title, max_length=MAX_TITLE_LENGTH, field="title"),
        "content": sanitize_text(content, field="content"),
        "category": sanitize_filename(category, field="category"),
        "tags": sanitize_tags(tags),
        "scope": sanitize_filename(scope, field="scope"),
    }


def validate_vault_write(folder: str, filename: str, content: str, tags: str) -> dict:
    """Validate all inputs for engram.vault_write."""
    return {
        "folder": sanitize_folder(folder),
        "filename": sanitize_filename(filename),
        "content": sanitize_text(content, field="content"),
        "tags": sanitize_tags(tags),
    }


def validate_add_memory(content: str, user_id: str) -> dict:
    """Validate all inputs for mem0.add_memory."""
    return {
        "content": sanitize_text(content, field="content"),
        "user_id": sanitize_user_id(user_id),
    }


def validate_request_context(query: str, intent: str) -> dict:
    """Validate all inputs for L5_routing.request_context."""
    valid_intents = frozenset({"answer", "plan", "review", "debug", "study"})
    return {
        "query": normalize_query(query),
        "intent": validate_enum(intent, valid_intents, "intent"),
    }


def validate_push_reminder(query: str, agent_id: str) -> dict:
    """Validate all inputs for L5_routing.push_reminder."""
    return {
        "query": sanitize_text(query, max_length=2000, field="query"),
        "agent_id": sanitize_user_id(agent_id),
    }


def validate_save_conversation(thread_id: str, messages_json: str) -> dict:
    """Validate all inputs for L2_conversations.save_conversation."""
    return {
        "thread_id": sanitize_thread_id(thread_id),
        "messages": validate_json_field(messages_json, "messages_json"),
    }


def validate_propose_change(session_id: str, title: str, changes_json: str) -> dict:
    """Validate all inputs for Lx_reasoning.propose_change_set."""
    changes = validate_json_field(changes_json, "changes_json")
    return {
        "session_id": sanitize_thread_id(session_id),
        "title": sanitize_text(title, max_length=MAX_TITLE_LENGTH, field="title"),
        "changes": changes,
    }
