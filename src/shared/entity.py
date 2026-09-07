"""Deterministic entity extraction — no LLM, no embeddings.

Extracts technical entities from text using regex patterns + a seeded
technical dictionary. Used by:
  - memory_db._prepare_row (auto-extract on upsert)
  - retrieval (entity boost)
  - consolidation L2->L3 (episode entity extraction)

Naming conventions:
  - CamelCaseWord (starts with uppercase, contains lowercase) -> class/function
  - UPPER_SNAKE_CASE (2+ uppercase chars) -> constant/module
  - Known technical terms from dictionary -> concept/pattern

Usage:
    from shared.entity import extract_entities, ENTITY_DICT

    entities = extract_entities("AuthService implements JWT authentication")
    # -> [{"name": "AuthService", "type": "class"}, {"name": "JWT", "type": "concept"}]
"""

from __future__ import annotations

import re
from typing import Any

# -- Technical dictionary (EN + ES) --------------------------------

ENTITY_DICT: dict[str, str] = {
    # Authentication / Security
    "authentication": "concept",
    "authorization": "concept",
    "jwt": "concept",
    "oauth": "concept",
    "token": "concept",
    "session": "concept",
    "credential": "concept",
    "password": "concept",
    "hash": "concept",
    "encryption": "concept",
    "ssl": "concept",
    "tls": "concept",
    "certificate": "concept",
    "mfa": "concept",
    "sso": "concept",
    # Database
    "database": "concept",
    "db": "concept",
    "sqlite": "concept",
    "postgres": "concept",
    "postgresql": "concept",
    "mongodb": "concept",
    "redis": "concept",
    "cache": "concept",
    "migration": "concept",
    "schema": "concept",
    "index": "concept",
    "query": "concept",
    "orm": "concept",
    "sql": "concept",
    "nosql": "concept",
    # API / Web
    "api": "concept",
    "rest": "concept",
    "graphql": "concept",
    "endpoint": "concept",
    "route": "concept",
    "middleware": "concept",
    "handler": "concept",
    "controller": "concept",
    "serializer": "concept",
    "validator": "concept",
    "request": "concept",
    "response": "concept",
    "payload": "concept",
    # Architecture
    "service": "concept",
    "module": "concept",
    "package": "concept",
    "library": "concept",
    "framework": "concept",
    "component": "concept",
    "plugin": "concept",
    "adapter": "concept",
    "factory": "concept",
    "repository": "concept",
    "strategy": "concept",
    "observer": "concept",
    "singleton": "concept",
    # Testing
    "test": "concept",
    "unit": "concept",
    "integration": "concept",
    "e2e": "concept",
    "mock": "concept",
    "fixture": "concept",
    "assertion": "concept",
    "coverage": "concept",
    # Errors / Debugging
    "error": "concept",
    "exception": "concept",
    "bug": "concept",
    "crash": "concept",
    "trace": "concept",
    "log": "concept",
    "debug": "concept",
    "stack": "concept",
    "retry": "concept",
    "timeout": "concept",
    # Deployment / Infra
    "docker": "concept",
    "kubernetes": "concept",
    "k8s": "concept",
    "ci": "concept",
    "cd": "concept",
    "pipeline": "concept",
    "deployment": "concept",
    "container": "concept",
    "image": "concept",
    "registry": "concept",
    "server": "concept",
    "client": "concept",
    "daemon": "concept",
    "process": "concept",
    "thread": "concept",
    "async": "concept",
    # Language-specific
    "python": "concept",
    "typescript": "concept",
    "javascript": "concept",
    "rust": "concept",
    "go": "concept",
    "pydantic": "concept",
    "fastapi": "concept",
    "pytest": "concept",
    "sqlalchemy": "concept",
    # Spanish
    "autenticar": "concept",
    "autenticación": "concept",
    "base de datos": "concept",
    "servicio": "concept",
    "módulo": "concept",
    "paquete": "concept",
    "excepción": "concept",
    "prueba": "concept",
    "implementar": "concept",
    "configuración": "concept",
    "sesión": "concept",
    "usuario": "concept",
    "función": "concept",
    "clase": "concept",
    "método": "concept",
}

# Compile patterns once at import time
_CAMEL_CASE_RE = re.compile(r'[A-Z][a-z]+(?:[A-Z][a-z]+)*')
_UPPER_SNAKE_RE = re.compile(r'[A-Z]{2,}(?:_[A-Z0-9]+)*')
_WORD_RE = re.compile(r'\b[a-zA-Záéíóúñü]{3,}\b')


def extract_entities(text: str) -> list[dict[str, Any]]:
    """Extract technical entities from text using regex + dictionary matching.

    Returns a list of {name, type} dicts, deduplicated and sorted.
    Type inference:
      - CamelCase -> 'class' or 'function' (heuristic: if ends with common suffixes)
      - UPPER_SNAKE -> 'constant' or 'module'
      - Known dict terms -> their mapped type
      - Other matches -> 'concept'
    """
    entities: dict[str, str] = {}

    # 1. CamelCase extraction - match complete CamelCase words
    # Use word boundaries to avoid matching substrings like "Lite" from "SQLite"
    _FULL_CAMEL_RE = re.compile(r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)*\b|\b[A-Z]{2,}(?:_[A-Z0-9]+)*\b')
    for match in _FULL_CAMEL_RE.finditer(text):
        name = match.group()
        if name.lower() in ENTITY_DICT:
            entity_type = ENTITY_DICT[name.lower()]
        elif len(name) >= 3:
            entity_type = "class"
        else:
            continue
        if name not in entities:
            entities[name] = entity_type

    # 2. UPPER_SNAKE_CASE extraction
    for match in _UPPER_SNAKE_RE.finditer(text):
        name = match.group()
        if name.lower() in ENTITY_DICT:
            entity_type = ENTITY_DICT[name.lower()]
        elif "_" in name:
            entity_type = "module"
        else:
            entity_type = "constant"
        if name not in entities:
            entities[name] = entity_type

    # 3. Lowercase dictionary matching
    text_lower = text.lower()
    for term, etype in ENTITY_DICT.items():
        if term in text_lower and term not in entities:
            entities[term] = etype

    return [{"name": name, "type": etype} for name, etype in sorted(entities.items())]


def extract_entity_names(text: str) -> list[str]:
    """Return just the entity names (for query expansion)."""
    return [e["name"] for e in extract_entities(text)]


def infer_entity_type(name: str) -> str:
    """Infer entity type from naming convention alone."""
    if name == name.upper() and "_" in name:
        return "module"
    if "_" in name:
        return "module"
    if name[0].isupper() and any(c.islower() for c in name[1:]):
        return "class"
    return "concept"
