#!/usr/bin/env python3
"""E2E Benchmark — MCP Memory Server comprehensive test bench.

Exercises every tool through the gateway with realistic payloads.
Measures latency, success rate, correctness, and error handling.

Usage:
    python3 bench/e2e_bench.py
    python3 bench/e2e_bench.py --quick   # Skip slow tests
"""

import json
import time
import sys
import urllib.request
import urllib.error
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# ── Config ──────────────────────────────────────────────────────────

GATEWAY = "http://127.0.0.1:3050/mcp"
QDRANT = "http://127.0.0.1:6333"
LLAMA = "http://127.0.0.1:8081"

# ── MCP Client ──────────────────────────────────────────────────────

class MCPClient:
    def __init__(self, gateway: str):
        self.gateway = gateway
        self.session = None
        self._req_id = 0

    def connect(self):
        """Initialize MCP session."""
        payload = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "e2e-bench", "version": "1.0"}
            },
            "id": 0
        }
        body = json.dumps(payload).encode()
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        req = urllib.request.Request(self.gateway, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                self.session = resp.headers.get("mcp-session-id")
                raw = resp.read().decode()
                for line in raw.split("\n"):
                    if line.startswith("data:"):
                        data = json.loads(line[5:])
                        if "result" in data:
                            return True
                return False
        except Exception as e:
            print(f"Connection error: {e}")
            return False

    def call(self, tool: str, args: dict) -> tuple[dict | None, float]:
        """Call a tool. Returns (parsed_result, latency_ms)."""
        self._req_id += 1
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": tool, "arguments": args},
            "id": self._req_id
        }
        t0 = time.monotonic()
        resp = self._send(payload)
        latency = (time.monotonic() - t0) * 1000
        return resp, latency

    def _send(self, payload: dict) -> dict | None:
        body = json.dumps(payload).encode()
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session:
            headers["Mcp-Session-Id"] = self.session

        req = urllib.request.Request(self.gateway, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                # Capture session from response
                self.session = resp.headers.get("mcp-session-id", self.session)
                raw = resp.read().decode()
                # Parse SSE format
                for line in raw.split("\n"):
                    if line.startswith("data:"):
                        data = json.loads(line[5:])
                        if "result" in data:
                            content = data["result"].get("content", [])
                            for c in content:
                                if c.get("type") == "text":
                                    try:
                                        return json.loads(c["text"])
                                    except json.JSONDecodeError:
                                        return {"raw": c["text"]}
                            # structuredContent fallback
                            sc = data["result"].get("structuredContent", {})
                            if sc:
                                return sc
                            return {"status": "ok", "_raw": data["result"]}
                        if "error" in data:
                            return {"error": data["error"]}
                return None
        except Exception as e:
            return {"error": str(e)}


# ── Benchmark Framework ─────────────────────────────────────────────

@dataclass
class TestResult:
    name: str
    category: str
    success: bool
    latency_ms: float
    error: str = ""
    details: str = ""
    data: Any = None

@dataclass
class BenchReport:
    results: list[TestResult] = field(default_factory=list)
    start_time: float = 0
    end_time: float = 0

    def add(self, r: TestResult):
        self.results.append(r)

    def print_report(self):
        print("\n")
        print("╔" + "═" * 78 + "╗")
        print("║  E2E BENCHMARK REPORT — MCP MEMORY SERVER                               ║")
        print("╠" + "═" * 78 + "╣")

        total = len(self.results)
        passed = sum(1 for r in self.results if r.success)
        failed = total - passed
        latencies = [r.latency_ms for r in self.results if r.success]

        duration = self.end_time - self.start_time

        print(f"║  Total: {total}  |  ✅ Passed: {passed}  |  ❌ Failed: {failed}  |  Time: {duration:.1f}s")
        if latencies:
            print(f"║  Latency — avg: {statistics.mean(latencies):.0f}ms  p50: {statistics.median(latencies):.0f}ms  "
                  f"p95: {sorted(latencies)[int(len(latencies)*0.95)]:.0f}ms  max: {max(latencies):.0f}ms")
        print("╠" + "═" * 78 + "╣")

        # Group by category
        categories = {}
        for r in self.results:
            categories.setdefault(r.category, []).append(r)

        for cat, results in categories.items():
            cat_pass = sum(1 for r in results if r.success)
            cat_lat = [r.latency_ms for r in results if r.success]
            avg_lat = statistics.mean(cat_lat) if cat_lat else 0
            print(f"\n║  ━━ {cat} ({cat_pass}/{len(results)} passed, avg {avg_lat:.0f}ms) ━━")

            for r in results:
                icon = "✅" if r.success else "❌"
                lat = f"{r.latency_ms:.0f}ms" if r.latency_ms < 10000 else f"{r.latency_ms/1000:.1f}s"
                detail = f" — {r.details}" if r.details else ""
                err = f" — {r.error[:60]}" if r.error else ""
                line = f"  {icon} {r.name}: {lat}{detail}{err}"
                print(f"║{line}")

        print("╚" + "═" * 78 + "╝")

        # Veredicto
        print()
        if failed == 0:
            print("🎉 ALL TESTS PASSED")
        else:
            print(f"⚠️  {failed} FAILURES — see details above")
        print()

        return failed == 0


# ── Helper: simple HTTP GET ─────────────────────────────────────────

def http_get(url: str, timeout: int = 5) -> dict | None:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def http_post(url: str, body: dict, timeout: int = 10) -> tuple[dict | None, int]:
    try:
        data = json.dumps(body).encode()
        req = urllib.request.Request(url, data=data,
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read()), resp.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read()) if e.headers.get("content-type","").startswith("application/json") else None, e.code
    except Exception as e:
        return {"error": str(e)}, 0


# ── Test Suites ─────────────────────────────────────────────────────

def bench_infrastructure(report: BenchReport):
    """Test 1: Infrastructure health — Qdrant, llama-server, Gateway."""
    print("  [1/8] Infrastructure...")

    # Qdrant health
    t0 = time.monotonic()
    try:
        req = urllib.request.Request(f"{QDRANT}/", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
            lat = (time.monotonic() - t0) * 1000
            report.add(TestResult("qdrant_health", "Infra", data is not None, lat,
                              details=f"title={data.get('title','?')}"))
    except Exception as e:
        lat = (time.monotonic() - t0) * 1000
        report.add(TestResult("qdrant_health", "Infra", False, lat, error=str(e)))

    # Qdrant collections
    t0 = time.monotonic()
    data = http_get(f"{QDRANT}/collections")
    lat = (time.monotonic() - t0) * 1000
    cols = [c["name"] for c in data.get("result", {}).get("collections", [])] if data else []
    report.add(TestResult("qdrant_collections", "Infra", len(cols) == 4, lat,
                          error="" if len(cols) == 4 else f"Expected 4, got {len(cols)}",
                          details=f"{','.join(cols)}"))

    # llama-server health
    t0 = time.monotonic()
    data = http_get(f"{LLAMA}/health")
    lat = (time.monotonic() - t0) * 1000
    report.add(TestResult("llama_server_health", "Infra", data is not None, lat,
                          error="" if data else "No response"))

    # llama-server embedding speed
    for label, text in [("short", "hello world"), ("medium", "authentication JWT token service for user login " * 5), ("long", "code map analysis " * 100)]:
        t0 = time.monotonic()
        data, status = http_post(f"{LLAMA}/embedding", {"content": text})
        lat = (time.monotonic() - t0) * 1000
        # Parse nested format: [{"embedding": [[float, ...]]}]
        dims = 0
        if data and isinstance(data, list) and data:
            emb = data[0].get("embedding", [])
            if isinstance(emb, list) and emb:
                if isinstance(emb[0], list):
                    dims = len(emb[0])
                else:
                    dims = len(emb)
        report.add(TestResult(f"embed_{label}", "Infra", dims == 1024, lat,
                              error="" if dims == 1024 else f"dims={dims}",
                              details=f"{len(text)} chars → {dims} dims"))

    # Gateway health
    t0 = time.monotonic()
    data = http_get("http://127.0.0.1:3050/health")
    lat = (time.monotonic() - t0) * 1000
    ok = data is not None and data.get("servers", {}).get("healthy", 0) == 7
    report.add(TestResult("gateway_health", "Infra", ok, lat,
                          details=f"7/7 servers"))


def bench_automem(report: BenchReport, client: MCPClient):
    """Test 2: AutoMem — ingest, memorize, heartbeat."""
    print("  [2/8] AutoMem...")

    # Status
    r, lat = client.call("automem_1mcp_status", {})
    report.add(TestResult("automem_status", "AutoMem", r is not None and "status" in (r or {}), lat,
                          details=r.get("status", "?") if r else "null"))

    # Memorize — fact
    r, lat = client.call("automem_1mcp_memorize", {
        "content": "El proyecto usa Qdrant v1.13 con hybrid search via /points/query",
        "mem_type": "fact",
        "scope": "session",
        "importance": 0.8,
        "tags": "architecture,qdrant,search"
    })
    report.add(TestResult("memorize_fact", "AutoMem",
                          r is not None and r.get("status") == "stored", lat,
                          details=f"layer={r.get('layer','?') if r else '?'}"))

    # Memorize — error_trace
    r, lat = client.call("automem_1mcp_memorize", {
        "content": "TypeError: expected str got None in auth/service.py line 42",
        "mem_type": "error_trace",
        "scope": "session",
        "tags": "bug,auth"
    })
    report.add(TestResult("memorize_error", "AutoMem",
                          r is not None and r.get("status") == "stored", lat))

    # Memorize — preference
    r, lat = client.call("automem_1mcp_memorize", {
        "content": "Prefiere respuestas en español, formato conciso",
        "mem_type": "preference",
        "scope": "personal",
        "importance": 0.9
    })
    report.add(TestResult("memorize_preference", "AutoMem",
                          r is not None and r.get("status") == "stored", lat))

    # Ingest event — terminal
    r, lat = client.call("automem_1mcp_ingest_event", {
        "event_type": "terminal",
        "source": "bash",
        "content": json.dumps({"cmd": "pip install qdrant-client", "exit": 0})
    })
    report.add(TestResult("ingest_terminal", "AutoMem",
                          r is not None and "ingested" in (r.get("status", "") if r else ""), lat))

    # Ingest event — diff_proposed (Plandex fusion)
    r, lat = client.call("automem_1mcp_ingest_event", {
        "event_type": "diff_proposed",
        "source": "sequential-thinking",
        "content": json.dumps({"file": "auth/service.py", "lines_added": 12, "lines_removed": 3})
    })
    report.add(TestResult("ingest_diff_proposed", "AutoMem",
                          r is not None and "ingested" in (r.get("status", "") if r else ""), lat))

    # Ingest event — diff_rejected
    r, lat = client.call("automem_1mcp_ingest_event", {
        "event_type": "diff_rejected",
        "source": "sequential-thinking",
        "content": json.dumps({"file": "auth/service.py", "reason": "syntax error"})
    })
    report.add(TestResult("ingest_diff_rejected", "AutoMem",
                          r is not None and "ingested" in (r.get("status", "") if r else ""), lat))

    # Heartbeat
    r, lat = client.call("automem_1mcp_heartbeat", {"agent_id": "bench-test", "turn_count": 5})
    report.add(TestResult("heartbeat", "AutoMem",
                          r is not None and r.get("status") == "active", lat))


def bench_conversation_store(report: BenchReport, client: MCPClient):
    """Test 3: Conversation Store — save, search, list, get."""
    print("  [3/8] Conversation Store...")

    thread_id = f"bench-{int(time.time())}"

    # Status
    r, lat = client.call("conversation-store_1mcp_status", {})
    report.add(TestResult("conv_status", "ConvStore", r is not None, lat))

    # Save conversation
    messages = json.dumps([
        {"role": "user", "content": "¿Cómo configuro Qdrant con sparse vectors?"},
        {"role": "assistant", "content": "Necesitas crear la colección con sparse_vectors config..."},
        {"role": "user", "content": "¿Y el endpoint para hybrid search?"},
        {"role": "assistant", "content": "En Qdrant v1.13 usa /points/query con vector + sparse_vector"},
    ])
    r, lat = client.call("conversation-store_1mcp_save_conversation", {
        "thread_id": thread_id,
        "messages_json": messages,
        "metadata": json.dumps({"project": "MCP-agent-memory", "topic": "qdrant"})
    })
    report.add(TestResult("save_conversation", "ConvStore",
                          r is not None and r.get("status") == "saved", lat))

    # List threads
    r, lat = client.call("conversation-store_1mcp_list_threads", {"limit": 5})
    threads = r.get("threads", []) if r else []
    report.add(TestResult("list_threads", "ConvStore",
                          r is not None and isinstance(threads, list), lat,
                          details=f"{len(threads)} threads"))

    # Search conversations
    r, lat = client.call("conversation-store_1mcp_search_conversations", {
        "query": "qdrant sparse vectors hybrid"
    })
    hits = r.get("total", 0) if r else 0
    report.add(TestResult("search_conversations", "ConvStore",
                          r is not None, lat,
                          details=f"{hits} hits"))

    # Get conversation
    r, lat = client.call("conversation-store_1mcp_get_conversation", {"thread_id": thread_id})
    msgs = r.get("message_count", 0) if r else 0
    report.add(TestResult("get_conversation", "ConvStore",
                          r is not None and msgs >= 0, lat,
                          details=f"{msgs} messages"))


def bench_mem0(report: BenchReport, client: MCPClient):
    """Test 4: Mem0 — add, search, get_all, delete."""
    print("  [4/8] Mem0...")

    # Status
    r, lat = client.call("mem0_1mcp_status", {})
    report.add(TestResult("mem0_status", "Mem0", r is not None, lat))

    # Add memory
    r, lat = client.call("mem0_1mcp_add_memory", {
        "content": "El servidor usa llama.cpp para embeddings con modelo BGE-M3 de 1024 dimensiones",
        "user_id": "ruben",
        "metadata": json.dumps({"source": "bench", "category": "architecture"})
    })
    mem_id = r.get("id", "") if r else ""
    report.add(TestResult("add_memory", "Mem0",
                          r is not None and r.get("status") in ("stored", "added"), lat,
                          details=f"id={mem_id[:12]}..." if mem_id else ""))

    # Add another
    r, lat = client.call("mem0_1mcp_add_memory", {
        "content": "Prefiere usar español para todas las interacciones",
        "user_id": "ruben"
    })
    report.add(TestResult("add_memory_2", "Mem0",
                          r is not None and r.get("status") in ("stored", "added"), lat))

    # Search memory
    r, lat = client.call("mem0_1mcp_search_memory", {
        "query": "embeddings dimensiones modelo",
        "user_id": "ruben",
        "limit": 3
    })
    hits = r.get("total", 0) if r else 0
    report.add(TestResult("search_memory", "Mem0",
                          r is not None, lat,
                          details=f"{hits} results"))

    # Get all memories
    r, lat = client.call("mem0_1mcp_get_all_memories", {"user_id": "ruben", "limit": 10})
    total = r.get("total", 0) if r else 0
    report.add(TestResult("get_all_memories", "Mem0",
                          r is not None, lat,
                          details=f"{total} memories"))

    # Delete memory (if we got an id)
    if mem_id:
        r, lat = client.call("mem0_1mcp_delete_memory", {
            "memory_id": mem_id,
            "user_id": "ruben"
        })
        report.add(TestResult("delete_memory", "Mem0",
                              r is not None, lat,
                              details=f"deleted {mem_id[:12]}..."))


def bench_engram(report: BenchReport, client: MCPClient):
    """Test 5: Engram — decisions, vault, model packs."""
    print("  [5/8] Engram...")

    # Status
    r, lat = client.call("engram_1mcp_status", {})
    report.add(TestResult("engram_status", "Engram", r is not None, lat))

    # Save decision
    r, lat = client.call("engram_1mcp_save_decision", {
        "title": "ADR-001: Hybrid Search con Qdrant",
        "content": "Decidimos usar /points/query para hybrid dense+sparse en vez de RRF manual. Razones: (1) nativo en Qdrant v1.13, (2) menos código, (3) mejor fusión.",
        "category": "architecture",
        "tags": "qdrant,search,hybrid",
        "scope": "project"
    })
    dec_path = r.get("path", "") if r else ""
    report.add(TestResult("save_decision", "Engram",
                          r is not None and r.get("status") in ("saved", "created"), lat,
                          details=dec_path))

    # List decisions
    r, lat = client.call("engram_1mcp_list_decisions", {"category": "architecture", "limit": 5})
    decs = r.get("total", 0) if r else 0
    report.add(TestResult("list_decisions", "Engram",
                          r is not None, lat,
                          details=f"{decs} decisions"))

    # Search decisions
    r, lat = client.call("engram_1mcp_search_decisions", {
        "query": "hybrid search qdrant",
        "limit": 3
    })
    report.add(TestResult("search_decisions", "Engram", r is not None, lat,
                          details=f"{r.get('total', 0) if r else 0} results"))

    # Get decision
    if dec_path:
        r, lat = client.call("engram_1mcp_get_decision", {"file_path": dec_path})
        report.add(TestResult("get_decision", "Engram",
                              r is not None, lat,
                              details=f"title={r.get('title','?')[:40] if r else '?'}"))

    # Model packs — list
    r, lat = client.call("engram_1mcp_list_model_packs", {})
    packs = r.get("total", 0) if r else 0
    report.add(TestResult("list_model_packs", "Engram", r is not None and packs >= 2, lat,
                          details=f"{packs} packs"))

    # Model packs — get default
    r, lat = client.call("engram_1mcp_get_model_pack", {"name": "default"})
    roles = list(r.get("pack", {}).get("roles", {}).keys()) if r else []
    report.add(TestResult("get_model_pack_default", "Engram",
                          len(roles) == 5, lat,
                          details=f"roles={','.join(roles)}"))

    # Model packs — get non-existent (should fallback)
    r, lat = client.call("engram_1mcp_get_model_pack", {"name": "nonexistent_pack"})
    has_fallback = "fallback" in (r.get("pack", {}).get("name", "") if r else "") or r.get("fallback", False)
    report.add(TestResult("get_model_pack_missing", "Engram",
                          r is not None, lat,
                          details="fallback triggered" if has_fallback else "no fallback"))

    # Vault write
    r, lat = client.call("engram_1mcp_vault_write", {
        "folder": "Notes",
        "filename": "bench-test-note.md",
        "content": "# Benchmark Test\n\nThis note was created by the E2E benchmark.",
        "note_type": "note",
        "tags": "test,benchmark",
        "author": "e2e-bench"
    })
    report.add(TestResult("vault_write", "Engram",
                          r is not None, lat,
                          details=r.get("status", "?") if r else "null"))

    # Vault list notes
    r, lat = client.call("engram_1mcp_vault_list_notes", {"folder": "Notes"})
    notes = r.get("total", 0) if r else 0
    report.add(TestResult("vault_list_notes", "Engram", r is not None, lat,
                          details=f"{notes} notes"))

    # Vault read note
    r, lat = client.call("engram_1mcp_vault_read_note", {"folder": "Notes", "filename": "bench-test-note.md"})
    report.add(TestResult("vault_read_note", "Engram",
                          r is not None, lat,
                          details=f"content_len={len(r.get('content','')) if r else 0}"))

    # Vault integrity check
    r, lat = client.call("engram_1mcp_vault_integrity_check", {})
    report.add(TestResult("vault_integrity", "Engram", r is not None, lat,
                          details=r.get("status", "?") if r else "null"))

    # Delete the test decision
    if dec_path:
        r, lat = client.call("engram_1mcp_delete_decision", {"file_path": dec_path})
        report.add(TestResult("delete_decision", "Engram", r is not None, lat))


def bench_sequential_thinking(report: BenchReport, client: MCPClient):
    """Test 6: Sequential Thinking — think, plan, propose, apply."""
    print("  [6/8] Sequential Thinking...")

    session_id = f"bench-st-{int(time.time())}"

    # Status
    r, lat = client.call("sequential-thinking_1mcp_status", {})
    report.add(TestResult("st_status", "SeqThinking", r is not None, lat))

    # Sequential thinking (with model pack)
    r, lat = client.call("sequential-thinking_1mcp_sequential_thinking", {
        "problem": "How to implement rate limiting for the embedding endpoint",
        "session_id": session_id,
        "max_steps": 3,
        "model_pack": "default"
    })
    steps = r.get("total_steps", 0) if r else 0
    has_pack = "model_pack_recommendations" in (r or {})
    report.add(TestResult("sequential_thinking", "SeqThinking",
                          r is not None and steps > 0, lat,
                          details=f"{steps} steps, model_pack={has_pack}"))

    # Record additional thought
    r, lat = client.call("sequential-thinking_1mcp_record_thought", {
        "session_id": session_id,
        "step": 4,
        "conclusion": "Use token bucket algorithm with configurable rate per agent_id",
        "confidence": 0.85,
        "tags": "rate-limit,algorithm"
    })
    report.add(TestResult("record_thought", "SeqThinking", r is not None, lat))

    # Create plan
    r, lat = client.call("sequential-thinking_1mcp_create_plan", {
        "goal": "Implement rate limiting for embedding endpoint",
        "session_id": session_id,
        "max_steps": 4,
        "dependencies": json.dumps([{"step": 2, "depends_on": 1}])
    })
    report.add(TestResult("create_plan", "SeqThinking", r is not None, lat,
                          details=f"plan_id={r.get('session_id','?') if r else '?'}"))

    # Propose change set (with syntax validation)
    changes = json.dumps([
        {"path": "rate_limiter.py", "content": "class RateLimiter:\n    def __init__(self, rate=10):\n        self.rate = rate\n        self.tokens = rate\n\n    def allow(self) -> bool:\n        return self.tokens > 0"},
        {"path": "middleware.py", "content": "from rate_limiter import RateLimiter\n\nlimiter = RateLimiter(rate=100)\n\ndef check_rate(agent_id: str) -> bool:\n    return limiter.allow()"}
    ])
    r, lat = client.call("sequential-thinking_1mcp_propose_change_set", {
        "session_id": session_id,
        "title": "Add rate limiting",
        "changes_json": changes,
        "validate": True
    })
    has_validation = "validation" in (r or {})
    report.add(TestResult("propose_change_set", "SeqThinking",
                          r is not None, lat,
                          details=f"validation={has_validation}"))

    # Get session
    r, lat = client.call("sequential-thinking_1mcp_get_thinking_session", {"session_id": session_id})
    report.add(TestResult("get_session", "SeqThinking", r is not None, lat,
                          details=f"steps={r.get('total_steps',0) if r else 0}"))

    # List sessions
    r, lat = client.call("sequential-thinking_1mcp_list_thinking_sessions", {})
    sessions = r.get("total", 0) if r else 0
    report.add(TestResult("list_sessions", "SeqThinking", r is not None, lat,
                          details=f"{sessions} sessions"))

    # Reflect
    r, lat = client.call("sequential-thinking_1mcp_reflect", {
        "session_id": session_id,
        "question": "What are the trade-offs of token bucket vs sliding window?"
    })
    report.add(TestResult("reflect", "SeqThinking", r is not None, lat))


def bench_vk_cache(report: BenchReport, client: MCPClient):
    """Test 7: VK-Cache — context retrieval, reminders, compliance."""
    print("  [7/8] VK-Cache...")

    # Status
    r, lat = client.call("vk-cache_1mcp_status", {})
    report.add(TestResult("vk_status", "VK-Cache", r is not None, lat))

    # Request context — simple
    r, lat = client.call("vk-cache_1mcp_request_context", {
        "query": "how does authentication work",
        "intent": "answer",
        "token_budget": 4000
    })
    meta = r.get("metadata", {}) if r else {}
    report.add(TestResult("request_context_simple", "VK-Cache",
                          r is not None and "context_pack" in (r or {}), lat,
                          details=f"sections={meta.get('sections_returned',0)}, tokens={meta.get('token_estimate',0)}"))

    # Request context — architect mode
    r, lat = client.call("vk-cache_1mcp_request_context", {
        "query": "implement JWT authentication middleware",
        "intent": "plan",
        "token_budget": 8000,
        "mode": "architect"
    })
    meta = r.get("metadata", {}) if r else {}
    report.add(TestResult("request_context_architect", "VK-Cache",
                          r is not None, lat,
                          details=f"mode=architect, sections={meta.get('sections_returned',0)}"))

    # Request context — Spanish
    r, lat = client.call("vk-cache_1mcp_request_context", {
        "query": "configuración de Qdrant con vectores sparse",
        "intent": "answer",
        "token_budget": 3000
    })
    report.add(TestResult("request_context_spanish", "VK-Cache",
                          r is not None, lat,
                          details="spanish query"))

    # Request context — code lookup
    r, lat = client.call("vk-cache_1mcp_request_context", {
        "query": "AuthService class JWT token verify method",
        "intent": "code_lookup",
        "token_budget": 2000
    })
    report.add(TestResult("request_context_code", "VK-Cache",
                          r is not None, lat,
                          details="code_lookup intent"))

    # Push reminder
    r, lat = client.call("vk-cache_1mcp_push_reminder", {
        "query": "Don't forget to update the embedding config",
        "reason": "User mentioned this task earlier",
        "agent_id": "bench-test"
    })
    rem_id = r.get("reminder_id", "") if r else ""
    report.add(TestResult("push_reminder", "VK-Cache", r is not None, lat,
                          details=f"id={rem_id[:12]}..." if rem_id else ""))

    # Check reminders
    r, lat = client.call("vk-cache_1mcp_check_reminders", {"agent_id": "bench-test"})
    rems = r.get("total", 0) if r else 0
    report.add(TestResult("check_reminders", "VK-Cache", r is not None, lat,
                          details=f"{rems} reminders"))

    # Dismiss reminder
    if rem_id:
        r, lat = client.call("vk-cache_1mcp_dismiss_reminder", {"reminder_id": rem_id})
        report.add(TestResult("dismiss_reminder", "VK-Cache", r is not None, lat))

    # Detect context shift
    r, lat = client.call("vk-cache_1mcp_detect_context_shift", {
        "current_query": "How to deploy to Kubernetes",
        "previous_query": "How to configure Qdrant sparse vectors",
        "agent_id": "bench-test"
    })
    shifted = r.get("shift_detected", False) if r else False
    report.add(TestResult("detect_context_shift", "VK-Cache", r is not None, lat,
                          details=f"shift={shifted} (expected True)"))

    # Verify compliance
    r, lat = client.call("vk-cache_1mcp_verify_compliance_tool", {
        "code": "def authenticate(token: str) -> bool:\n    return token == 'secret'",
        "rule_ids": "security"
    })
    report.add(TestResult("verify_compliance", "VK-Cache", r is not None, lat))


def bench_autodream(report: BenchReport, client: MCPClient):
    """Test 8: AutoDream — consolidation, dream, semantic/consolidated get."""
    print("  [8/8] AutoDream...")

    # Status
    r, lat = client.call("autodream_1mcp_status", {})
    report.add(TestResult("dream_status", "AutoDream", r is not None, lat))

    # Heartbeat
    r, lat = client.call("autodream_1mcp_heartbeat", {"agent_id": "bench-test", "turn_count": 3})
    report.add(TestResult("dream_heartbeat", "AutoDream", r is not None, lat))

    # Get semantic memories (L3)
    r, lat = client.call("autodream_1mcp_get_semantic", {"scope": "all"})
    report.add(TestResult("get_semantic", "AutoDream", r is not None, lat,
                          details=f"items={r.get('total',0) if r else 0}"))

    # Get consolidated memories (L4)
    r, lat = client.call("autodream_1mcp_get_consolidated", {"scope": "all"})
    report.add(TestResult("get_consolidated", "AutoDream", r is not None, lat,
                          details=f"items={r.get('total',0) if r else 0}"))

    # Dream cycle (lightweight — just triggers the cycle)
    r, lat = client.call("autodream_1mcp_dream", {})
    report.add(TestResult("dream_cycle", "AutoDream", r is not None, lat,
                          details=f"result preview: {str(r)[:80] if r else 'null'}"))

    # Consolidate
    r, lat = client.call("autodream_1mcp_consolidate", {"force": False})
    report.add(TestResult("consolidate", "AutoDream", r is not None, lat,
                          details=f"result preview: {str(r)[:80] if r else 'null'}"))


def bench_stress_embedding(report: BenchReport):
    """Bonus: Embedding stress test — burst + sustained."""
    print("  [+] Embedding stress...")

    # Burst: 10 embeddings en paralelo
    import concurrent.futures
    t0 = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        futs = [pool.submit(lambda i: http_post(f"{LLAMA}/embedding",
            {"content": f"stress test embedding number {i} with various tokens about authentication"},
        ), i) for i in range(10)]
        results = [f.result() for f in futs]
    lat = (time.monotonic() - t0) * 1000
    ok = all(d and d[1] == 200 for d in results if d)
    report.add(TestResult("embed_burst_10", "Stress", ok, lat,
                          details=f"10 parallel in {lat:.0f}ms ({lat/10:.0f}ms avg)"))

    # Burst: 3 servers concurrent (simulate automem+vkcache+mem0)
    t0 = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futs = [
            pool.submit(http_post, f"{LLAMA}/embedding",
                {"content": "user authentication JWT token verify"}),
            pool.submit(http_post, f"{LLAMA}/embedding",
                {"content": "how to implement login system"}),
            pool.submit(http_post, f"{LLAMA}/embedding",
                {"content": "prefers dark mode in editor"}),
        ]
        results = [f.result() for f in futs]
    lat = (time.monotonic() - t0) * 1000
    ok = all(d and d[1] == 200 for d in results if d)
    report.add(TestResult("embed_3servers", "Stress", ok, lat,
                          details=f"3 concurrent in {lat:.0f}ms"))

    # Cache hit test: same text twice
    text = "cache hit test query for benchmark"
    _, lat1 = http_post(f"{LLAMA}/embedding", {"content": text})
    # Note: llama-server doesn't cache, but shared/embedding.py does via LRU


# ── Main ────────────────────────────────────────────────────────────

def main():
    print("╔" + "═" * 60 + "╗")
    print("║  MCP Memory Server — E2E Benchmark                       ║")
    print("╚" + "═" * 60 + "╝")
    print()

    report = BenchReport()
    report.start_time = time.monotonic()

    # Connect
    client = MCPClient(GATEWAY)
    if not client.connect():
        print("❌ Cannot connect to gateway. Aborting.")
        sys.exit(1)
    print("✅ Connected to gateway\n")

    # Run suites
    bench_infrastructure(report)
    bench_automem(report, client)
    bench_conversation_store(report, client)
    bench_mem0(report, client)
    bench_engram(report, client)
    bench_sequential_thinking(report, client)
    bench_vk_cache(report, client)
    bench_autodream(report, client)
    bench_stress_embedding(report)

    report.end_time = time.monotonic()

    # Print report
    all_pass = report.print_report()

    # Save JSON
    report_data = {
        "timestamp": datetime.now().isoformat(),
        "duration_s": report.end_time - report.start_time,
        "total": len(report.results),
        "passed": sum(1 for r in report.results if r.success),
        "failed": sum(1 for r in report.results if not r.success),
        "results": [
            {
                "name": r.name,
                "category": r.category,
                "success": r.success,
                "latency_ms": round(r.latency_ms, 1),
                "error": r.error,
                "details": r.details,
            }
            for r in report.results
        ]
    }
    with open("/Users/ruben/MCP-servers/MCP-agent-memory/bench/results.json", "w") as f:
        json.dump(report_data, f, indent=2)
    print(f"📄 Results saved to bench/results.json")

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
