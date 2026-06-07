#!/usr/bin/env python3
"""Backpack Panel — telemetry collector + control/config server for MCP-agent-memory.

Read-only sensors against the live deployment plus measured active probes.
Serves the dashboard GUI, current metrics, rolling history, control actions
(whitelisted) and configuration editing (whitelisted keys, with .env backup).

Stdlib only. Binds to 127.0.0.1:8895.

Sensors (all real measurements, no estimates):
  S1  Service health + latency: backpack :8890, qdrant :6333, embeddings :8081,
      LLM :9000 (1-token completion, every 60 s), engram :3100.
  S2  Capture: events.jsonl tail parse — totals, 24 h volume, hourly buckets,
      type/source distributions, junk ratio (NOISE_PREFIXES match), last-event age.
  S3  Layers: exact Qdrant counts L1–L4 + L2_conversations + L3_facts.
  S4  Consolidation: state.json content + age (stall alarm), log error scan.
  S5  Retrieval probe: real request-context round-trips, rolling p50/p95/max.
  S6  Conversations: SQLite threads/messages + last-save age.
  S7  Entities: SQLite entities/events/relations.
  S8  Infra: file/DB/log sizes, WARN+error rate in backpack log, cache rows.
  S9  Zero-vector scan (every 120 s): samples L1 vectors from Qdrant and counts
      all-zero embeddings — direct measurement of P3 poison.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import threading
import time
import urllib.request
import urllib.error
from collections import deque
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE = Path.home() / "MCP-servers" / "MCP-agent-memory"
DATA = BASE / "data"
EVENTS = DATA / "L0-sensory" / "events.jsonl"
STATE = DATA / "L4-narrative" / "state.json"
CONV_DB = DATA / "conversations.db"
ENT_DB = DATA / "entity_timeline.db"
EMB_CACHE = BASE / "src" / "embedding_cache.db"
BACKPACK_LOG = DATA / "logs" / "backpack.stderr.log"
LOGS_DIR = DATA / "logs"
ENV_FILE = BASE / ".env"

PORT = 8895
POLL_S = 10
BACKPACK = "http://127.0.0.1:8890"
QDRANT = "http://127.0.0.1:6333"
EMB = "http://127.0.0.1:8081"
LLM = "http://127.0.0.1:9000"
ENGRAM = "http://127.0.0.1:3100"

NOISE_PREFIXES = ("bash: total ", "bash: drwx", "bash: -rw", "bash: lrwx",
                  "edit: Edit applied successfully.", "write: Wrote file successfully.",
                  "glob: ", "grep: Found ", "todowrite:", "read: <path>", "bash: DONE")

ACTION_WHITELIST = {
    "consolidate":      {"kind": "http", "url": f"{BACKPACK}/api/consolidate", "body": {"force": False}},
    "consolidate_force":{"kind": "http", "url": f"{BACKPACK}/api/consolidate", "body": {"force": True}},
    "heartbeat_dream":  {"kind": "http", "url": f"{BACKPACK}/api/heartbeat-dream", "body": {"agent_id": "panel", "turn_count": 0}},
    "probe_context":    {"kind": "http", "url": f"{BACKPACK}/api/request-context", "body": {"query": "panel probe: estado del proyecto", "agent_id": "panel", "token_budget": 1000}},
    "restart_backpack": {"kind": "launchctl", "svc": "com.agent-memory.backpack-api"},
    "restart_qdrant":   {"kind": "launchctl", "svc": "com.agent-memory.qdrant"},
    "restart_embedding":{"kind": "launchctl", "svc": "com.agent-memory.llama-embedding"},
    "restart_llm":      {"kind": "launchctl", "svc": "com.agent-memory.llama-llm"},
}
CONFIG_WHITELIST = ["CONSOLIDATION_PROMOTE_L1", "CONSOLIDATION_PROMOTE_L2", "CONSOLIDATION_PROMOTE_L3",
                    "CONSOLIDATION_PROMOTE_L4", "L5_ROUTING_MIN_SCORE", "L5_ROUTING_MAX_ITEMS",
                    "L5_ROUTING_MAX_TOKENS", "L0_CAPTURE_PROMOTE_EVERY", "EMBEDDING_DIM", "EMBEDDING_MODEL"]

METRICS: dict = {"ts": None, "starting": True}
HISTORY: deque = deque(maxlen=720)          # ~2 h at 10 s
RETR_LAT: deque = deque(maxlen=60)          # rolling retrieval latencies (ms)
SSE_CLIENTS: list = []                      # live push channels (Server-Sent Events)
_llm_last = {"t": 0.0, "ms": None, "ok": None}
_zv_last = {"t": 0.0, "sampled": 0, "zeros": 0}
_du_last = {"t": 0.0, "mb": None}
_lock = threading.Lock()


def http_json(url: str, body: dict | None = None, timeout: float = 6.0):
    """Return (ok, payload_or_error, latency_ms)."""
    t0 = time.time()
    try:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data,
                                     headers={"Content-Type": "application/json"} if data else {})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
        ms = (time.time() - t0) * 1000
        try:
            return True, json.loads(raw), ms
        except Exception:
            return True, raw.decode(errors="replace")[:200], ms
    except Exception as e:
        return False, str(e)[:200], (time.time() - t0) * 1000


def svc_health() -> dict:
    out = {}
    ok, _, ms = http_json(f"{BACKPACK}/api/health"); out["backpack"] = {"up": ok, "ms": round(ms, 1)}
    ok, _, ms = http_json(f"{QDRANT}/healthz");      out["qdrant"] = {"up": ok, "ms": round(ms, 1)}
    ok, d, ms = http_json(f"{EMB}/v1/embeddings", {"input": "panel-probe", "model": "bge-m3"}, timeout=8)
    nonzero = bool(ok and isinstance(d, dict) and any(abs(x) > 1e-9 for x in d["data"][0]["embedding"][:32]))
    out["embedding"] = {"up": ok, "ms": round(ms, 1), "nonzero": nonzero}
    now = time.time()
    if now - _llm_last["t"] > 60:                    # LLM probed each 60 s (1 token)
        ok, _, ms = http_json(f"{LLM}/v1/chat/completions",
                              {"messages": [{"role": "user", "content": "1"}], "max_tokens": 1}, timeout=20)
        _llm_last.update({"t": now, "ms": round(ms, 1), "ok": ok})
    out["llm"] = {"up": _llm_last["ok"], "ms": _llm_last["ms"]}
    ok, _, ms = http_json(f"{ENGRAM}/health", timeout=2); out["engram"] = {"up": ok, "ms": round(ms, 1)}
    return out


def capture_metrics() -> dict:
    out = {"total": None, "size_mb": None, "h24": 0, "per_hour": [], "types": {}, "sources": {},
           "junk_24h": 0, "junk_pct": None, "last_age_s": None}
    try:
        size = EVENTS.stat().st_size
        out["size_mb"] = round(size / 1e6, 2)
        with open(EVENTS, "rb") as f:                 # fast total line count
            out["total"] = sum(buf.count(b"\n") for buf in iter(lambda: f.read(1 << 20), b""))
        with open(EVENTS, "rb") as f:                 # parse only the tail (last 3 MB)
            if size > 3_000_000:
                f.seek(-3_000_000, 2); f.readline()
            lines = f.read().decode(errors="replace").splitlines()
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=24)
        buckets = [0] * 12                            # last 12 h, hourly
        last_ts = None
        for ln in lines:
            try:
                d = json.loads(ln)
                ts = datetime.fromisoformat(d.get("timestamp", "").replace("Z", "+00:00"))
            except Exception:
                continue
            last_ts = ts
            if ts < cutoff:
                continue
            out["h24"] += 1
            t = d.get("type", "?"); out["types"][t] = out["types"].get(t, 0) + 1
            s = d.get("source", "?"); out["sources"][s] = out["sources"].get(s, 0) + 1
            c = str((d.get("attributes") or {}).get("content", ""))
            if c.startswith(NOISE_PREFIXES) or c in ("bash: DONE", ""):
                out["junk_24h"] += 1
            age_h = (now - ts).total_seconds() / 3600
            if age_h < 12:
                buckets[11 - int(age_h)] += 1
        out["per_hour"] = buckets
        if out["h24"]:
            out["junk_pct"] = round(100 * out["junk_24h"] / out["h24"], 1)
        if last_ts:
            out["last_age_s"] = int((now - last_ts).total_seconds())
    except Exception as e:
        out["error"] = str(e)[:120]
    return out


def qdrant_metrics() -> dict:
    out = {"layers": {}, "conversations": None, "facts": None}
    for layer in (1, 2, 3, 4):
        ok, d, _ = http_json(f"{QDRANT}/collections/L0_L4_memory/points/count",
                             {"filter": {"must": [{"key": "layer", "match": {"value": layer}}]}, "exact": True})
        out["layers"][f"L{layer}"] = d["result"]["count"] if ok and isinstance(d, dict) else None
    for name, key in (("L2_conversations", "conversations"), ("L3_facts", "facts")):
        ok, d, _ = http_json(f"{QDRANT}/collections/{name}")
        out[key] = d["result"]["points_count"] if ok and isinstance(d, dict) else None
    return out


def consolidation_metrics() -> dict:
    out = {"state": None, "age_h": None, "last_error": None}
    try:
        out["state"] = json.loads(STATE.read_text())
        out["age_h"] = round((time.time() - STATE.stat().st_mtime) / 3600, 1)
    except Exception as e:
        out["state_error"] = str(e)[:120]
    try:                                              # last consolidation-related error in log tail
        with open(BACKPACK_LOG, "rb") as f:
            size = f.seek(0, 2)
            f.seek(max(0, size - 200_000))
            tail = f.read().decode(errors="replace")
        errs = [l for l in tail.splitlines() if "API error" in l]
        if errs:
            out["last_error"] = errs[-1][-180:]
        out["warn_tail"] = len(errs)
    except Exception:
        pass
    return out


def retrieval_probe() -> dict:
    q = ["estado del proyecto", "arquitectura de memoria", "decisiones recientes",
         "errores de consolidacion"][int(time.time() / POLL_S) % 4]
    ok, d, ms = http_json(f"{BACKPACK}/api/request-context",
                          {"query": f"panel probe: {q}", "agent_id": "panel", "token_budget": 1200}, timeout=8)
    sources = None
    if ok and isinstance(d, dict):
        sources = len((d.get("context_pack") or {}).get("sources") or [])
        RETR_LAT.append(ms)
    lat = sorted(RETR_LAT)
    p = lambda f: round(lat[min(len(lat) - 1, int(len(lat) * f))], 1) if lat else None
    return {"ok": ok, "last_ms": round(ms, 1), "p50": p(0.5), "p95": p(0.95),
            "max": round(lat[-1], 1) if lat else None, "sources": sources, "samples": len(lat)}


def sqlite_metrics() -> dict:
    out = {}
    try:
        c = sqlite3.connect(f"file:{CONV_DB}?mode=ro", uri=True, timeout=2)
        out["threads"] = c.execute("SELECT count(*) FROM threads").fetchone()[0]
        out["messages"] = c.execute("SELECT count(*) FROM messages").fetchone()[0]
        last = c.execute("SELECT max(updated_at) FROM threads").fetchone()[0]
        if last:
            dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            out["last_save_h"] = round((datetime.now(timezone.utc) - dt).total_seconds() / 3600, 1)
        c.close()
    except Exception as e:
        out["conv_error"] = str(e)[:100]
    try:
        c = sqlite3.connect(f"file:{ENT_DB}?mode=ro", uri=True, timeout=2)
        out["entities"] = c.execute("SELECT count(*) FROM entities").fetchone()[0]
        out["entity_events"] = c.execute("SELECT count(*) FROM entity_events").fetchone()[0]
        try:
            out["relations"] = c.execute("SELECT count(*) FROM entity_relations").fetchone()[0]
        except Exception:
            out["relations"] = None
        c.close()
    except Exception as e:
        out["ent_error"] = str(e)[:100]
    try:
        c = sqlite3.connect(f"file:{EMB_CACHE}?mode=ro", uri=True, timeout=2)
        out["emb_cache_rows"] = c.execute("SELECT count(*) FROM embeddings").fetchone()[0]
        c.close()
    except Exception:
        out["emb_cache_rows"] = None
    return out


def infra_metrics() -> dict:
    out = {"files": {}, "qdrant_mb": None}
    for label, p in (("events.jsonl", EVENTS), ("conversations.db", CONV_DB),
                     ("entity_timeline.db", ENT_DB), ("embedding_cache.db", EMB_CACHE),
                     ("backpack.log", BACKPACK_LOG),
                     ("llama-llm.log", LOGS_DIR / "llama-llm.stderr.log"),
                     ("llama-emb.log", LOGS_DIR / "llama-embedding.stderr.log")):
        try:
            out["files"][label] = round(p.stat().st_size / 1e6, 1)
        except Exception:
            out["files"][label] = None
    now = time.time()
    if now - _du_last["t"] > 300:                     # du is heavy → every 5 min
        try:
            r = subprocess.run(["du", "-sm", str(BASE / "storage")],
                               capture_output=True, text=True, timeout=20)
            _du_last.update({"t": now, "mb": int(r.stdout.split()[0]) if r.returncode == 0 else None})
        except Exception:
            _du_last.update({"t": now})
    out["qdrant_mb"] = _du_last["mb"]
    return out


def zero_vector_scan() -> dict:
    """S9 — direct measurement of embedding poison (every 120 s)."""
    now = time.time()
    if now - _zv_last["t"] > 120:
        ok, d, _ = http_json(f"{QDRANT}/collections/L0_L4_memory/points/scroll",
                             {"limit": 150, "with_vector": True, "with_payload": False,
                              "filter": {"must": [{"key": "layer", "match": {"value": 1}}]}}, timeout=15)
        if ok and isinstance(d, dict):
            pts = d["result"]["points"]
            zeros = 0
            for p in pts:
                v = p.get("vector")
                if isinstance(v, dict):
                    v = v.get("") or next(iter(v.values()), [])
                if v and all(abs(x) < 1e-9 for x in v[:64]):
                    zeros += 1
            _zv_last.update({"t": now, "sampled": len(pts), "zeros": zeros})
        else:
            _zv_last["t"] = now
    s, z = _zv_last["sampled"], _zv_last["zeros"]
    return {"sampled": s, "zeros": z, "pct": round(100 * z / s, 2) if s else None}


def compute_alarms(m: dict) -> list:
    a = []
    cons = m.get("consolidation", {})
    if cons.get("age_h") is not None and cons["age_h"] > 48:
        a.append({"sev": "crit", "msg": f"Consolidación parada: state.json lleva {cons['age_h']} h sin escribirse (F-01)"})
    if cons.get("last_error") and "_load_state" in cons["last_error"]:
        a.append({"sev": "crit", "msg": "NameError _load_state activo en el log — el fix F-01 sigue pendiente"})
    for k, v in (m.get("services") or {}).items():
        if v.get("up") is False and k != "engram":
            a.append({"sev": "crit", "msg": f"Servicio caído: {k}"})
    if (m.get("services", {}).get("engram", {}) or {}).get("up") is False:
        a.append({"sev": "warn", "msg": "Engram (:3100) caído — F-09, el plugin degrada en silencio"})
    cap = m.get("capture", {})
    if cap.get("junk_pct") is not None and cap["junk_pct"] > 30:
        a.append({"sev": "warn", "msg": f"Ruido en captura 24 h: {cap['junk_pct']}% del contenido es basura (F-06)"})
    zv = m.get("zero_vectors", {})
    if zv.get("zeros"):
        a.append({"sev": "crit", "msg": f"Vectores-cero detectados en L1: {zv['zeros']}/{zv['sampled']} muestreados (P3)"})
    r = m.get("retrieval", {})
    if r.get("p95") and r["p95"] > 1500:
        a.append({"sev": "warn", "msg": f"Recuperación lenta: p95 {r['p95']} ms (timeout plugin 3000 ms)"})
    ly = (m.get("qdrant") or {}).get("layers") or {}
    if ly.get("L1") and ly.get("L2") is not None and ly["L1"] > 200 * max(ly["L2"], 1):
        a.append({"sev": "warn", "msg": f"Backlog L1 desbordado: {ly['L1']} vs L2 {ly['L2']} — consolidación no drena"})
    emb = (m.get("services") or {}).get("embedding") or {}
    if emb.get("up") and emb.get("nonzero") is False:
        a.append({"sev": "crit", "msg": "El servidor de embeddings devuelve vectores cero — contaminación activa (P3)"})
    return a


def poll_loop():
    global METRICS
    while True:
        t0 = time.time()
        m = {"ts": datetime.now(timezone.utc).isoformat(),
             "services": svc_health(), "capture": capture_metrics(),
             "qdrant": qdrant_metrics(), "consolidation": consolidation_metrics(),
             "retrieval": retrieval_probe(), "store": sqlite_metrics(),
             "infra": infra_metrics(), "zero_vectors": zero_vector_scan()}
        m["alarms"] = compute_alarms(m)
        m["poll_ms"] = round((time.time() - t0) * 1000)
        with _lock:
            METRICS = m
            HISTORY.append({"ts": m["ts"],
                            "h24": m["capture"].get("h24"),
                            "last_hour": (m["capture"].get("per_hour") or [0])[-1],
                            "retr_ms": m["retrieval"].get("last_ms"),
                            "L1": m["qdrant"]["layers"].get("L1"),
                            "L2": m["qdrant"]["layers"].get("L2"),
                            "alarms": len(m["alarms"])})
            payload = "data: " + json.dumps(m, default=str) + "\n\n"
            for q in list(SSE_CLIENTS):               # instant push to connected panels
                q.append(payload)
        time.sleep(max(1, POLL_S - (time.time() - t0)))


def tail_loop():
    """Real-time capture beacon: tails events.jsonl and pushes every new event
    to connected panels as an SSE `capture` frame (≤0.5 s latency, read-only)."""
    pos = None
    while True:
        try:
            size = EVENTS.stat().st_size
            if pos is None:
                pos = size                            # start at EOF: only NEW events
            if size > pos:
                with open(EVENTS, "rb") as f:
                    f.seek(pos)
                    chunk = f.read(min(size - pos, 200_000))
                    pos = f.tell()
                for ln in chunk.decode(errors="replace").splitlines():
                    try:
                        d = json.loads(ln)
                    except Exception:
                        continue
                    evt = {"ts": d.get("timestamp"), "type": d.get("type"),
                           "source": d.get("source"),
                           "subtype": (d.get("attributes") or {}).get("event_subtype"),
                           "session": (d.get("session_id") or "")[:20],
                           "content": str((d.get("attributes") or {}).get("content", ""))[:140]}
                    frame = "event: capture\ndata: " + json.dumps(evt) + "\n\n"
                    with _lock:
                        for q in list(SSE_CLIENTS):
                            q.append(frame)
            elif size < pos:                          # rotation/truncation
                pos = size
        except Exception:
            pass
        time.sleep(0.5)


def read_config() -> dict:
    out = {"file": str(ENV_FILE), "keys": {}}
    try:
        txt = ENV_FILE.read_text() if ENV_FILE.exists() else ""
        if not txt:
            out["note"] = ".env no existe aún — al guardar una clave se creará (el daemon lo carga via env_loader al reiniciar)"
        for k in CONFIG_WHITELIST:
            mt = re.search(rf"^{k}=(.*)$", txt, re.M)
            out["keys"][k] = mt.group(1).strip() if mt else None
    except Exception as e:
        out["error"] = str(e)[:120]
    return out


def write_config(key: str, value: str) -> dict:
    if key not in CONFIG_WHITELIST:
        return {"ok": False, "error": f"key not whitelisted: {key}"}
    if not re.fullmatch(r"[A-Za-z0-9_.:/\- ]{0,120}", value):
        return {"ok": False, "error": "invalid value"}
    txt = ENV_FILE.read_text() if ENV_FILE.exists() else ""
    backup = ENV_FILE.with_suffix(f".env.bak-{int(time.time())}")
    backup.write_text(txt)                            # backup before every write (empty if new)
    if re.search(rf"^{key}=", txt, re.M):
        txt = re.sub(rf"^{key}=.*$", f"{key}={value}", txt, flags=re.M)
    else:
        txt = txt.rstrip("\n") + f"\n{key}={value}\n"
    ENV_FILE.write_text(txt)
    return {"ok": True, "backup": backup.name, "note": "Reinicia backpack-api para aplicar"}


def run_action(name: str) -> dict:
    spec = ACTION_WHITELIST.get(name)
    if not spec:
        return {"ok": False, "error": f"action not whitelisted: {name}"}
    if spec["kind"] == "http":
        ok, d, ms = http_json(spec["url"], spec["body"], timeout=120)
        return {"ok": ok, "ms": round(ms), "response": d if isinstance(d, dict) else str(d)[:400]}
    if spec["kind"] == "launchctl":
        uid = os.getuid()
        r = subprocess.run(["launchctl", "kickstart", "-k", f"gui/{uid}/{spec['svc']}"],
                           capture_output=True, text=True, timeout=30)
        return {"ok": r.returncode == 0, "stdout": r.stdout[-200:], "stderr": r.stderr[-200:]}
    return {"ok": False, "error": "unknown kind"}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, payload, ctype="application/json"):
        body = payload if isinstance(payload, bytes) else json.dumps(payload, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            try:
                html = (Path(__file__).parent / "dashboard.html").read_bytes()
                self._send(200, html, "text/html; charset=utf-8")
            except Exception as e:
                self._send(500, {"error": str(e)})
        elif self.path == "/metrics":
            with _lock:
                self._send(200, METRICS)
        elif self.path == "/history":
            with _lock:
                self._send(200, list(HISTORY))
        elif self.path == "/api/config":
            self._send(200, read_config())
        elif self.path == "/stream":                  # SSE: instant metric push
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            q: deque = deque(maxlen=50)
            with _lock:
                q.append("data: " + json.dumps(METRICS, default=str) + "\n\n")
                SSE_CLIENTS.append(q)
            try:
                while True:
                    if q:
                        self.wfile.write(q.popleft().encode())
                        self.wfile.flush()
                    else:
                        time.sleep(0.2)
            except Exception:
                pass
            finally:
                with _lock:
                    if q in SSE_CLIENTS:
                        SSE_CLIENTS.remove(q)
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            self._send(400, {"error": "invalid body"}); return
        if self.path == "/api/action":
            self._send(200, run_action(str(body.get("action", ""))))
        elif self.path == "/api/config":
            self._send(200, write_config(str(body.get("key", "")), str(body.get("value", ""))))
        else:
            self._send(404, {"error": "not found"})

    def log_message(self, *a):                        # quiet
        pass


if __name__ == "__main__":
    threading.Thread(target=poll_loop, daemon=True).start()
    threading.Thread(target=tail_loop, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Backpack Panel on http://127.0.0.1:{PORT}")
    srv.serve_forever()
