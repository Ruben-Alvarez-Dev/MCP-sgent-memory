"""Synonym dictionary for query expansion.

Provides bidirectional lookup between technical terms and their aliases.
Used by the retrieval pipeline to expand queries before FTS5 search.

Seed data covers common technical terminology in EN and ES.
The dictionary is read-only at runtime - additions require code change.

Usage:
    from shared.synonym import expand_query, get_expanded_tokens

    query = "how do we auth users"
    expanded = expand_query(query)
    # -> "authentication auth jwt token ..."
"""

from __future__ import annotations

import re

# -- Synonym map: term -> pipe-separated aliases ----------------------

_SYNONYM_MAP: dict[str, str] = {
    # Auth / Security
    "auth": "authentication|authorization|jwt|token|login|oauth|credential|sso|mfa",
    "authentication": "auth|authorization|jwt|token|login|oauth",
    "authorization": "auth|authentication|jwt|permission|access",
    "jwt": "json web token|auth|token|authentication",
    "oauth": "auth|authentication|token|sso",
    "login": "auth|signin|authentication|log in",
    "logout": "auth|signout|log out|sign out",
    "session": "auth|token|cookie|user session",
    "password": "passwd|credential|secret",
    "permission": "access|privilege|role|authorization",
    "role": "permission|access|privilege",
    # Database
    "database": "db|datastore|persist|storage|repo",
    "db": "database|datastore|persist",
    "sqlite": "database|db|storage|persist",
    "postgres": "postgresql|database|db|pgsql",
    "postgresql": "postgres|postgresql|database|db",
    "mongodb": "mongo|db|database|nosql",
    "redis": "cache|store|database|key-value",
    "cache": "redis|memory|buffer|store",
    "migration": "migrate|schema change|db update|alembic",
    "orm": "sqlalchemy|mapper|query builder|database abstraction",
    "sql": "query|database|select|postgresql",
    "nosql": "mongodb|redis|cassandra|document store",
    # API / Web
    "api": "endpoint|rest|graphql|service|interface",
    "endpoint": "api|route|path|handler",
    "route": "path|endpoint|url|api",
    "middleware": "interceptor|hook|pipeline|filter",
    "handler": "controller|processor|handler function",
    "controller": "handler|view|router",
    "serializer": "encoder|marshal|format converter",
    "validator": "checker|verifier|sanitizer",
    "request": "http request|call|inbound",
    "response": "http response|reply|outbound",
    # Architecture
    "service": "component|module|handler|backend",
    "module": "package|library|component|unit",
    "class": "type|object|entity|model",
    "function": "func|method|routine|procedure",
    "method": "function|func|routine",
    "interface": "contract|api|protocol|abstract",
    "dependency": "dep|requirement|import|lib",
    # Testing
    "test": "spec|assertion|check|verification",
    "unit test": "unit|test|verification",
    "integration": "integration test|e2e|smoke",
    "mock": "stub|fake|dummy|simulate",
    "fixture": "test data|setup|seed|precondition",
    # Errors
    "error": "exception|fault|failure|bug|issue",
    "exception": "error|exception type|throw|raise",
    "bug": "defect|issue|fault|error",
    "crash": "crash|fatal|panic|abort",
    "trace": "stack trace|traceback|debug|log",
    # Deployment
    "deploy": "deployment|release|ship|rollout",
    "docker": "container|image|dockerfile",
    "kubernetes": "k8s|cluster|orchestrator",
    "pipeline": "ci|cd|build|workflow",
    # Spanish
    "autenticar": "auth|authentication|login|jwt",
    "autenticación": "auth|authentication|login|jwt",
    "base de datos": "database|db|sqlite|postgres|sql",
    "servicio": "service|component|module|backend",
    "módulo": "module|package|component|library",
    "paquete": "package|module|library",
    "excepción": "exception|error|throw|raise",
    "prueba": "test|spec|verification|unit test",
    "implementar": "implement|develop|build|create",
    "configuración": "config|configuration|settings|setup",
    "sesión": "session|auth|token|user session",
    "usuario": "user|account|profile|member",
    "función": "function|func|method|routine",
    "clase": "class|type|object|entity",
    "método": "method|function|func|routine",
}

# Build reverse map for fast lookup
_REVERSE_MAP: dict[str, str] = {}
for term, aliases in _SYNONYM_MAP.items():
    _REVERSE_MAP[term] = aliases
    for alias in aliases.split("|"):
        alias_lower = alias.strip().lower()
        if alias_lower not in _REVERSE_MAP:
            _REVERSE_MAP[alias_lower] = term

# Compile token pattern
_TOKEN_RE = re.compile(r'[a-zA-Záéíóúñü]{3,}')


def expand_query(query: str) -> str:
    """Expand a query string using the synonym dictionary.

    Tokenizes the query, looks up each token in the synonym map,
    and returns an expanded FTS5-compatible query string.

    Args:
        query: Raw user query string.

    Returns:
        Expanded query string with synonyms OR'd together.
    """
    tokens = _TOKEN_RE.findall(query.lower())
    expanded: set[str] = set()

    for token in tokens:
        expanded.add(token)  # Always keep the original token
        # Check direct map first (token is a key like "auth")
        if token in _SYNONYM_MAP:
            for alias in _SYNONYM_MAP[token].split("|"):
                alias_clean = alias.strip().lower()
                if alias_clean and alias_clean != token and alias_clean not in expanded:
                    expanded.add(alias_clean)
        # Check reverse map (token is an alias like "jwt" -> original "auth")
        elif token in _REVERSE_MAP:
            original_term = _REVERSE_MAP[token]
            if original_term in _SYNONYM_MAP:
                for alias in _SYNONYM_MAP[original_term].split("|"):
                    alias_clean = alias.strip().lower()
                    if alias_clean and alias_clean != token and alias_clean not in expanded:
                        expanded.add(alias_clean)

    return " ".join(sorted(expanded))


def get_expanded_tokens(query: str) -> list[str]:
    """Return expanded tokens as a list (for debugging / testing)."""
    return expand_query(query).split()
