#!/usr/bin/env python3
"""metrics.py — panel operativo de MCP-agent-memory.

Responde "¿funciona y de qué manera?":
  --snapshot           Adopción (usage.jsonl) + crecimiento DB + umbrales.
                       Añade una línea a data/metrics/history.jsonl.
  --benchmark N [N...]  Latencias reales vía protocolo MCP contra sandbox:
                       upsert de N memorias sintéticas → p50/p95 de
                       add/search/request-context. Limpia al terminar.

Umbrales (alerta):
  - huérfanos FTS (índice sin punto) > 0        → integridad
  - DB > 500 MB                                  → crecimiento
  - search p95 > 200 ms con 1k memorias          → eficiencia
  - tasa de error de tools > 1% (24h)            → fiabilidad
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYTHON = REPO / ".venv" / "bin" / "python3"
SERVER = REPO / "src" / "unified" / "server" / "main.py"


def base_dir() -> Path:
    base = os.getenv("MEMORY_SERVER_DIR") or os.path.expanduser("~/.memory")
    data = os.getenv("DATA_DIR") or str(Path(base) / "data")
    return Path(data)


def pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round(p / 100 * (len(s) - 1)))))
    return s[k]


# ── snapshot ──────────────────────────────────────────────────────────────


def cmd_snapshot() -> int:
    data = base_dir()
    db = data / "memory.db"
    usage_file = data / "metrics" / "usage.jsonl"
    print(f"═══ snapshot {time.strftime('%Y-%m-%d %H:%M:%S')} ═══")
    alerts: list[str] = []

    # adopción
    calls: dict[str, list[float]] = {}
    errs = 0
    total = 0
    last24 = 0
    if usage_file.exists():
        cutoff24 = time.time() - 86400
        for line in usage_file.read_text().splitlines():
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            total += 1
            calls.setdefault(rec["tool"], []).append(rec["ms"])
            if not rec.get("ok", True):
                errs += 1
            if rec["ts"] >= cutoff24:
                last24 += 1
    print(f"\n── adopción ({total} llamadas registradas, {last24} en 24h)")
    if calls:
        for tool, lat in sorted(calls.items(), key=lambda kv: -len(kv[1])):
            print(f"  {tool:<42} {len(lat):>6} llamadas  p50={pct(lat,50):7.1f}ms  p95={pct(lat,95):7.1f}ms")
    else:
        print("  (sin telemetría aún — los contadores empiezan con este build)")

    # crecimiento
    print("\n── crecimiento")
    db_mb = db.stat().st_size / 1e6 if db.exists() else 0.0
    print(f"  memory.db: {db_mb:.2f} MB")
    counts = {}
    if db.exists():
        import sqlite3

        conn = sqlite3.connect(db)
        for table in ("points", "threads", "messages"):
            try:
                counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            except sqlite3.OperationalError:
                counts[table] = 0
        try:
            counts["points_fts"] = conn.execute("SELECT COUNT(*) FROM points_fts").fetchone()[0]
        except sqlite3.OperationalError:
            counts["points_fts"] = 0
        conn.close()
    print(f"  points={counts.get('points',0)}  fts={counts.get('points_fts',0)}  "
          f"threads={counts.get('threads',0)}  messages={counts.get('messages',0)}")
    orphans = counts.get("points_fts", 0) - counts.get("points", 0)
    if orphans > 0:
        alerts.append(f"FTS huérfanos: {orphans} (integridad)")
    if db_mb > 500:
        alerts.append(f"DB {db_mb:.0f} MB (>500 MB)")

    # umbrales de latencia según telemetría propia
    for tool, lat in calls.items():
        if "search" in tool and len(lat) >= 10 and pct(lat, 95) > 200:
            alerts.append(f"{tool} p95={pct(lat,95):.0f}ms > 200ms")
    if total and errs / total > 0.01:
        alerts.append(f"tasa de error {errs/total:.1%} > 1%")

    # history
    hist = data / "metrics" / "history.jsonl"
    hist.parent.mkdir(parents=True, exist_ok=True)
    with open(hist, "a") as f:
        f.write(json.dumps({"ts": time.time(), "total_calls": total, "db_mb": round(db_mb, 2),
                            "points": counts.get("points", 0), "fts": counts.get("points_fts", 0),
                            "alerts": alerts}) + "\n")

    print("\n── veredicto")
    if alerts:
        for a in alerts:
            print(f"  ⚠️  {a}")
        return 1
    print("  ✅ todo dentro de umbrales")
    return 0


# ── benchmark ─────────────────────────────────────────────────────────────


WORDS = ["quantum", "ledger", "migration", "vault", "isolation", "token", "parser",
         "pipeline", "retry", "cache", "schema", "daemon", "consolidation", "scope",
         "decision", "rollback", "broker", "throttle", "index", "recovery"]


def _spawn_server(sandbox: str):
    env = dict(os.environ)
    env.update({"PYTHONPATH": str(REPO / "src"), "MEMORY_SERVER_DIR": sandbox,
                "DATA_DIR": os.path.join(sandbox, "data"), "MEMORY_API_DISABLED": "1"})
    for k in ("MEMORY_AGENT_ID", "MEMORY_AGENT_TOKEN", "MEMORY_IDENTITY_MODE"):
        env.pop(k, None)
    p = subprocess.Popen([str(PYTHON), "-u", str(SERVER)], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         text=True, env=env, cwd=str(REPO))

    def send(o):
        p.stdin.write(json.dumps(o) + "\n")
        p.stdin.flush()

    send({"jsonrpc": "2.0", "id": 0, "method": "initialize",
          "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                     "clientInfo": {"name": "bench", "version": "1"}}})
    json.loads(p.stdout.readline())
    send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    counter = [0]

    def call(tool, args):
        counter[0] += 1
        send({"jsonrpc": "2.0", "id": counter[0], "method": "tools/call",
              "params": {"name": tool, "arguments": args}})
        while True:
            r = json.loads(p.stdout.readline())
            if "id" in r:
                txt = "".join(c.get("text", "") for c in r.get("result", {}).get("content", []))
                try:
                    return json.loads(txt)
                except json.JSONDecodeError:
                    return {"__raw__": txt}

    return p, call


def cmd_benchmark(scales: list[int], probes: int) -> int:
    print(f"═══ benchmark de latencia (protocolo MCP real, sandbox) ═══")
    print(f"{'N memorias':>10} | {'add p50':>9} {'p95':>9} | {'search p50':>10} {'p95':>9} | {'context':>8}")
    print("-" * 72)
    ok_all = True
    for n in scales:
        sandbox = tempfile.mkdtemp(prefix="metrics-bench-")
        os.makedirs(os.path.join(sandbox, "config"))
        os.makedirs(os.path.join(sandbox, "data"))
        p, call = _spawn_server(sandbox)
        try:
            t_adds: list[float] = []
            t0 = time.perf_counter()
            for i in range(n):
                w = " ".join(WORDS[(i + j) % len(WORDS)] for j in range(4))
                t = time.perf_counter()
                call("L3_facts_add_memory", {"content": f"bench{i} {w} memory {i}", "user_id": "bench"})
                t_adds.append((time.perf_counter() - t) * 1000)
            load_s = time.perf_counter() - t0

            t_search: list[float] = []
            for i in range(probes):
                q = f"bench{uuid.randbytes(2).hex()}" if False else f"memory {i % n} {WORDS[i % len(WORDS)]}"
                t = time.perf_counter()
                call("L3_facts_search_memory", {"query": q, "user_id": "bench", "limit": 5})
                t_search.append((time.perf_counter() - t) * 1000)

            t_ctx: list[float] = []
            for i in range(min(probes, 10)):
                t = time.perf_counter()
                call("L5_routing_request_context", {"query": f"memory {i % n}", "token_budget": 2000})
                t_ctx.append((time.perf_counter() - t) * 1000)

            ctx_s = f"{pct(t_ctx,50):7.1f}ms" if t_ctx else "      —"
            print(f"{n:>10} | {pct(t_adds,50):>8.1f}ms {pct(t_adds,95):>8.1f}ms | "
                  f"{pct(t_search,50):>9.1f}ms {pct(t_search,95):>8.1f}ms | {ctx_s}")
            print(f"{'':>10} | (carga de {n} memorias en {load_s:.1f}s)")
            if n >= 1000 and pct(t_search, 95) > 200:
                print(f"{'':>10} | ⚠️  search p95 > 200ms con {n} memorias")
                ok_all = False
        finally:
            p.terminate()
            shutil.rmtree(sandbox, ignore_errors=True)
    return 0 if ok_all else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--snapshot", action="store_true", help="adopción + crecimiento + umbrales")
    ap.add_argument("--benchmark", nargs="+", type=int, metavar="N",
                    help="latencias con N memorias sintéticas (p.ej. --benchmark 100 1000 3000)")
    ap.add_argument("--probes", type=int, default=20, help="búsquedas por escala (default 20)")
    args = ap.parse_args()
    if args.benchmark:
        return cmd_benchmark(args.benchmark, args.probes)
    return cmd_snapshot()


if __name__ == "__main__":
    raise SystemExit(main())
