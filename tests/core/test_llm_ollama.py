"""Tests for shared/llm/ollama.py and factory routing — no network, no services.

Uses httpx.MockTransport injected into OllamaBackend (production code always
uses the real transport; injection here is test-only wiring, not a fake in prod).
"""
import json
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from shared import model_tier
from shared.config import Config
from shared.llm import get_llm
from shared.llm.base import LLMModelNotFoundError, LLMUnavailableError
from shared.llm.ollama import OllamaBackend


# ── Transport builders ─────────────────────────────────────────────────

def _ok_transport(tags=("qwen2.5:7b",), content="pong"):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": t} for t in tags]})
        if request.url.path == "/api/chat":
            body = json.loads(request.content)
            return httpx.Response(200, json={
                "model": body["model"],
                "message": {"role": "assistant", "content": content},
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 5,
                "eval_count": 7,
            })
        if request.url.path == "/api/generate":
            return httpx.Response(200, json={
                "model": "qwen2.5:7b",
                "response": content,
                "done": True,
                "done_reason": "stop",
            })
        return httpx.Response(404, json={"error": f"unknown path {request.url.path}"})
    return httpx.MockTransport(handler)


def _down_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")
    return httpx.MockTransport(handler)


@pytest.fixture()
def offline_resolver(tmp_path, monkeypatch):
    """Swap the module singleton for one confined to tmp_path with no backends.

    Keeps notify_backend_failure() (called on connection errors) from probing
    the real machine or writing into the repo's data/ directory.
    """
    cfg = Config(
        server_dir=str(tmp_path),
        data_dir=str(tmp_path / "data"),
        L0_events_jsonl=str(tmp_path / "data" / "events.jsonl"),
    )
    resolver = model_tier.TierResolver(config=cfg, ttl_seconds=3600.0)
    resolver._probe_hardware = lambda: {
        "hostname": "test-host", "os": "darwin", "arch": "x86_64",
        "cpu": "Test CPU", "logical_cores": 8,
        "ram_total_gb": 16.0, "ram_available_gb": 8.0, "gpu_class": "none",
    }
    resolver._probe_backends = lambda: (
        model_tier.BackendMap(
            ollama=model_tier.BackendStatus(reachable=False, detail="ConnectError"),
            llama_server=model_tier.BackendStatus(reachable=False),
            llama_cpp_local=model_tier.BackendStatus(reachable=False),
        ),
        [],
    )
    monkeypatch.setattr(model_tier, "_resolver", resolver)
    return resolver


# ── Backend behavior ───────────────────────────────────────────────────

class TestOllamaBackendChat:
    def test_chat_parses_native_response(self):
        backend = OllamaBackend(
            url="http://ollama.test", model="qwen2.5:7b", transport=_ok_transport()
        )
        resp = backend.chat([{"role": "user", "content": "ping"}])
        assert resp.content == "pong"
        assert resp.model == "qwen2.5:7b"
        assert resp.finish_reason == "stop"
        assert resp.usage == {"input_tokens": 5, "output_tokens": 7, "total_tokens": 12}

    def test_ask_wraps_chat(self):
        backend = OllamaBackend(
            url="http://ollama.test", model="qwen2.5:7b", transport=_ok_transport()
        )
        assert backend.ask("ping") == "pong"

    def test_generate_uses_native_endpoint(self):
        backend = OllamaBackend(
            url="http://ollama.test", model="qwen2.5:7b", transport=_ok_transport()
        )
        resp = backend.generate("ping")
        assert resp.content == "pong"
        assert resp.finish_reason == "stop"

    def test_stream_yields_chunks(self):
        lines = (
            json.dumps({"model": "qwen2.5:7b", "message": {"content": "po"}, "done": False})
            + "\n"
            + json.dumps({
                "model": "qwen2.5:7b", "message": {"content": "ng"},
                "done": True, "done_reason": "stop",
            })
            + "\n"
        )

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/tags":
                return httpx.Response(200, json={"models": [{"name": "qwen2.5:7b"}]})
            return httpx.Response(200, content=lines.encode())

        backend = OllamaBackend(
            url="http://ollama.test", model="qwen2.5:7b",
            transport=httpx.MockTransport(handler),
        )
        chunks = list(backend.stream([{"role": "user", "content": "ping"}]))
        assert "".join(c.delta for c in chunks) == "pong"
        assert chunks[-1].finish_reason == "stop"


class TestOllamaBackendErrors:
    def test_missing_model_raises_typed_error(self):
        backend = OllamaBackend(
            url="http://ollama.test", model="qwen3.5:4b",
            transport=_ok_transport(tags=("qwen2.5:7b",)),
        )
        with pytest.raises(LLMModelNotFoundError, match="qwen3.5:4b"):
            backend.chat([{"role": "user", "content": "ping"}])

    def test_missing_model_error_is_unavailable_subtype(self):
        assert issubclass(LLMModelNotFoundError, LLMUnavailableError)

    def test_is_available_false_when_down(self):
        backend = OllamaBackend(url="http://ollama.test", transport=_down_transport())
        assert backend.is_available() is False

    def test_is_available_true_when_up(self):
        backend = OllamaBackend(url="http://ollama.test", transport=_ok_transport())
        assert backend.is_available() is True

    def test_chat_when_down_raises_unavailable_and_notifies_resolver(
        self, offline_resolver
    ):
        backend = OllamaBackend(
            url="http://ollama.test", model="qwen2.5:7b", transport=_down_transport()
        )
        with pytest.raises(LLMUnavailableError, match="unreachable"):
            backend.chat([{"role": "user", "content": "ping"}])
        # Reactive hook re-probed and resolved the injected T0 environment
        assert offline_resolver.resolve().tier == "T0"


# ── Factory routing ────────────────────────────────────────────────────

class TestFactoryRouting:
    def test_explicit_ollama_backend(self, monkeypatch):
        monkeypatch.setenv("LLM_BACKEND", "ollama")
        assert isinstance(get_llm(), OllamaBackend)

    def test_explicit_argument_wins(self, monkeypatch):
        monkeypatch.delenv("LLM_BACKEND", raising=False)
        assert isinstance(get_llm(backend="ollama"), OllamaBackend)

    def test_no_backend_and_t0_resolver_raises_unavailable(
        self, monkeypatch, offline_resolver
    ):
        monkeypatch.delenv("LLM_BACKEND", raising=False)
        with pytest.raises(LLMUnavailableError):
            get_llm()

    def test_no_backend_prefers_ollama_when_reachable(
        self, monkeypatch, offline_resolver
    ):
        monkeypatch.delenv("LLM_BACKEND", raising=False)
        offline_resolver._probe_backends = lambda: (
            model_tier.BackendMap(
                ollama=model_tier.BackendStatus(reachable=True, url="http://ollama.test"),
                llama_server=model_tier.BackendStatus(reachable=False),
                llama_cpp_local=model_tier.BackendStatus(reachable=False),
            ),
            ["qwen2.5:7b"],
        )
        offline_resolver.force_refresh()
        assert isinstance(get_llm(), OllamaBackend)
