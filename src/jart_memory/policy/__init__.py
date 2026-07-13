"""Framework-independent authorization policies."""

from .isolation import AccessDecision, IsolationPolicy, MemoryAccessDenied, MemoryOwner

__all__ = ["AccessDecision", "IsolationPolicy", "MemoryAccessDenied", "MemoryOwner"]
