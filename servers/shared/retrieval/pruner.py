"""Token pruning helpers for dense context assembly."""

from __future__ import annotations

import ast
import re
from pathlib import Path


_TS_LINE_COMMENT = re.compile(r"^\s*//")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_PY_DEF = re.compile(r"^(\s*)(async\s+def|def)\s+([A-Za-z_]\w*)\s*\(.*", re.MULTILINE)
_TS_DEF = re.compile(
    r"^(\s*)(export\s+)?(async\s+)?(function|const|class)\s+([A-Za-z_]\w*)",
    re.MULTILINE,
)


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _strip_python_comments(text: str) -> str:
    lines = [line for line in text.splitlines() if not line.lstrip().startswith("#")]
    return "\n".join(lines)


def _strip_generic_comments(text: str) -> str:
    lines = [line for line in text.splitlines() if not _TS_LINE_COMMENT.match(line)]
    return _BLOCK_COMMENT.sub("", "\n".join(lines))


def _collapse_python_bodies(text: str) -> str:
    try:
        tree = ast.parse(text)
        # Advanced AST-based collapsing
        return _collapse_python_bodies_ast(text)
    except Exception:
        # Fallback to regex-based collapsing if syntax is invalid
        lines = text.splitlines()
        collapsed: list[str] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            match = _PY_DEF.match(line)
            if not match:
                collapsed.append(line)
                i += 1
                continue
            indent = len(match.group(1))
            collapsed.append(line)
            i += 1
            body_seen = False
            while i < len(lines):
                next_line = lines[i]
                if (
                    next_line.strip()
                    and (len(next_line) - len(next_line.lstrip())) <= indent
                ):
                    break
                if next_line.strip() and not body_seen:
                    collapsed.append(" " * (indent + 4) + "...")
                    body_seen = True
                i += 1
        return "\n".join(collapsed)


def _collapse_python_bodies_ast(text: str) -> str:
    tree = ast.parse(text)
    rendered: list[str] = []
    module_doc = ast.get_docstring(tree, clean=False)
    if module_doc:
        rendered.append(f'"""{module_doc}"""\n')

    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            # Keep signature, stub body
            sig = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
            if isinstance(node, ast.ClassDef):
                sig = f"class {node.name}:"
            else:
                sig += f"def {node.name}(...):"
            rendered.append(sig)
            doc = ast.get_docstring(node)
            if doc:
                rendered.append(f'    """{doc}"""')
            rendered.append("    ...\n")
        else:
            # For variables/imports, keep them if small
            pass
    return "\n".join(rendered)


def _truncate_preserving_lines(text: str, max_tokens: int) -> str:
    max_chars = max_tokens * 4
    kept: list[str] = []
    current = 0
    for line in text.splitlines():
        if current + len(line) > max_chars:
            break
        kept.append(line)
        current += len(line) + 1
    return "\n".join(kept) + ("\n..." if len(kept) < len(text.splitlines()) else "")


def prune_content(
    text: str, path: str = "", max_tokens: int = 4000, is_rule: bool = False
) -> str:
    """Reduce content size while keeping high-signal information.

    If is_rule=True, it prioritizes semantic integrity over token limits
    (i.e., it avoids cutting rules in the middle).
    """
    if estimate_tokens(text) <= max_tokens:
        return text

    # Rules are special: we don't collapse them, we either keep them or we don't.
    if is_rule:
        # For rules, we try to at least keep the first few whole rules (lines)
        return _truncate_preserving_lines(text, max_tokens)

    suffix = Path(path).suffix.lower()
    if suffix == ".py":
        pruned = _strip_python_comments(text)
        try:
            pruned = _collapse_python_bodies(pruned)
        except Exception:
            pass
    else:
        pruned = _strip_generic_comments(text)

    if estimate_tokens(pruned) <= max_tokens:
        return pruned

    return _truncate_preserving_lines(pruned, max_tokens)
