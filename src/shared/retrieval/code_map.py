from __future__ import annotations
import ast
import hashlib
import re
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field
from pygments import lex
from pygments.lexers import get_lexer_for_filename, guess_lexer, ClassNotFound
from pygments.token import Token
import datetime
from zoneinfo import ZoneInfo

# --- Pydantic Models (SPEC-1.1) ---

class CodeSymbol(BaseModel):
    """A single symbol extracted from a source code file."""
    name: str
    type: str
    line: int
    signature: str = ""
    parent: Optional[str] = None
    visibility: str = "public"

class CodeMap(BaseModel):
    """A compact, syntax-aware map of a source code file."""
    file_path: str
    sha: str
    language: str
    lines_total: int
    imports: List[str] = Field(default_factory=list)
    exports: List[str] = Field(default_factory=list)
    symbols: List[CodeSymbol] = Field(default_factory=list)
    summary: str
    map_text: str
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(ZoneInfo("UTC")).isoformat())

# --- Helper Functions ---

def _format_map_text(code_map: CodeMap) -> str:
    try:
        relative_path = Path(code_map.file_path).relative_to(Path.cwd())
    except ValueError:
        relative_path = Path(code_map.file_path).name

    lines = [f"{relative_path} ({code_map.lines_total} lines, {code_map.language})"]
    if code_map.imports:
        lines.append(f"  imports: {', '.join(sorted(list(set(code_map.imports))))}")
    
    symbols_by_parent = {}
    standalone_symbols = []
    for s in code_map.symbols:
        if s.parent:
            symbols_by_parent.setdefault(s.parent, []).append(s)
        else:
            standalone_symbols.append(s)

    for symbol in sorted(standalone_symbols, key=lambda s: s.line):
         lines.append(f"  {symbol.signature or symbol.name}")

    for parent, child_symbols in sorted(symbols_by_parent.items()):
        lines.append(f"  {parent}")
        for symbol in sorted(child_symbols, key=lambda s: s.line):
            lines.append(f"    {symbol.signature or symbol.name}")
    return "\n".join(lines)

def _python_map(content: str, path: Path, sha: str) -> Optional[CodeMap]:
    try:
        tree = ast.parse(content)
        imports = set()
        symbols = []
        
        class SymbolVisitor(ast.NodeVisitor):
            def __init__(self):
                self.current_class = None

            def visit_ClassDef(self, node):
                symbols.append(CodeSymbol(name=node.name, type="class", line=node.lineno, signature=f"class {node.name}"))
                self.current_class = node.name
                self.generic_visit(node)
                self.current_class = None

            def visit_FunctionDef(self, node):
                self._process_function(node)

            def visit_AsyncFunctionDef(self, node):
                self._process_function(node)

            def _process_function(self, node):
                signature = ast.get_source_segment(content, node).splitlines()[0]
                if signature.strip().startswith('@'):
                    signature = "def " + signature.split("def ")[-1] if "def " in signature else signature
                
                symbol_type = "method" if self.current_class else "function"
                parent_sig = f"class {self.current_class}" if self.current_class else None
                symbols.append(CodeSymbol(name=node.name, type=symbol_type, line=node.lineno, signature=signature.strip().rstrip(':'), parent=parent_sig))

            def visit_Import(self, node):
                for alias in node.names:
                    imports.add(alias.name)
            
            def visit_ImportFrom(self, node):
                if node.module:
                    imports.add(node.module)

        SymbolVisitor().visit(tree)
        
        lines_total = len(content.splitlines())
        summary = f"{path.name}: {lines_total} lines, {len(symbols)} symbols found."
        
        code_map = CodeMap(file_path=str(path), sha=sha, language="python", lines_total=lines_total, imports=list(imports), symbols=symbols, summary=summary, map_text="")
        code_map.map_text = _format_map_text(code_map)
        return code_map
    except (SyntaxError, ValueError):
        return None

def _pygments_map(content: str, path: Path, sha: str) -> Optional[CodeMap]:
    try:
        lexer = get_lexer_for_filename(str(path), code=content)
    except ClassNotFound:
        try:
            lexer = guess_lexer(content)
        except ClassNotFound:
            return None

    language = lexer.name.lower().replace(' ', '-')
    tokens = list(lex(content, lexer))
    symbols = []
    
    i = 0
    while i < len(tokens):
        ttype, tvalue = tokens[i]
        
        if ttype in Token.Keyword and tvalue in ('class', 'function', 'export', 'async'):
            # Look ahead to find the name
            j = i + 1
            # Skip over intermediate keywords/whitespace like 'async function' or 'default'
            while j < len(tokens) and not (tokens[j][0] in Token.Name):
                j += 1
            
            if j < len(tokens) and tokens[j][0] in Token.Name:
                name = tokens[j][1]
                
                # Determine type by looking at the keywords between start and name
                stype = 'function' # Default
                keyword_slice = [t[1] for t in tokens[i:j]]
                if 'class' in keyword_slice:
                    stype = 'class'

                if not any(s.name == name for s in symbols):
                    symbols.append(CodeSymbol(name=name, type=stype, line=0))
                i = j
                continue

        i += 1

    lines_total = len(content.splitlines())
    summary = f"{path.name}: {lines_total} lines, {len(symbols)} symbols found."
    code_map = CodeMap(file_path=str(path), sha=sha, language=language, lines_total=lines_total, symbols=symbols, summary=summary, map_text="")
    code_map.map_text = _format_map_text(code_map)
    return code_map

def generate_code_map(file_path: str) -> Optional[CodeMap]:
    path = Path(file_path)
    if not path.is_file():
        return None
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        sha = hashlib.sha256(content.encode()).hexdigest()[:12]
        if path.suffix == ".py":
            return _python_map(content, path, sha)
        else:
            return _pygments_map(content, path, sha)
    except Exception:
        return None
