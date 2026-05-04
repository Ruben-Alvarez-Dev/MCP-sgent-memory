"""App test fixtures — requires Qdrant (:6333) and embedding server (:8081)."""
import sys
import os
import pytest

# Ensure src/ is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

# Skip entire app suite if services aren't running
import httpx
def _services_available():
    try:
        r = httpx.get("http://127.0.0.1:6333/healthz", timeout=2)
        if r.status_code != 200:
            return False
    except Exception:
        return False
    try:
        r = httpx.get("http://127.0.0.1:8081/health", timeout=2)
        if "ok" not in r.text:
            return False
    except Exception:
        return False
    return True

if not _services_available():
    pytest.skip("App tests require Qdrant (:6333) and embedding server (:8081)", allow_module_level=True)
