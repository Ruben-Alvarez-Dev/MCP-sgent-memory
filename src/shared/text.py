"""Smart text truncation for embedding — preserves sentence boundaries.

Used by embedding.py to truncate long content without breaking sentences.
Head+tail strategy: keep beginning and end, skip the middle.
"""
from __future__ import annotations

import re


def smart_truncate(text: str, max_chars: int = 2000) -> str:
    """Truncate text intelligently for embedding.

    Strategy:
    1. If fits in max_chars, return as-is.
    2. Try to cut at last sentence boundary (., !, ?) within limit.
    3. If no sentence boundary, try paragraph break.
    4. If nothing works, use head+tail (first 60% + last 30%).

    Returns text that fits within max_chars.
    """
    if len(text) <= max_chars:
        return text

    # Strategy 1: Cut at last sentence boundary
    # Look for . ! ? followed by space or end
    truncated = text[:max_chars]
    sentence_end = truncated.rfind(". ")
    alt_end = truncated.rfind("! ")
    alt_end2 = truncated.rfind("? ")
    best_end = max(sentence_end, alt_end, alt_end2)

    if best_end > max_chars * 0.5:
        return truncated[:best_end + 1].strip()

    # Strategy 2: Cut at last paragraph break
    para_end = truncated.rfind("\n\n")
    if para_end > max_chars * 0.5:
        return truncated[:para_end].strip()

    # Strategy 3: Cut at last newline
    nl_end = truncated.rfind("\n")
    if nl_end > max_chars * 0.5:
        return truncated[:nl_end].strip()

    # Strategy 4: Head + tail (keep start and end, skip middle)
    head_size = int(max_chars * 0.6)
    tail_size = int(max_chars * 0.3)
    head = text[:head_size]
    tail = text[-tail_size:]
    return head + "\n\n[...truncated...]\n\n" + tail
