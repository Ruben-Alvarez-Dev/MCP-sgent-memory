"""Unified Health Check — MCP Memory Server.

Checks all critical services and reports status.
Can be used as a CLI tool or imported as a module.

Usage:
    python3 -m shared.health
    python3 -m shared.health --json
    python3 -m shared.health --watch  (continuous monitoring)

Services checked:
    1. Qdrant       — http://127.0.0.1:6333
    2. llama-server  — http://127.0.0.1:8081
    3. 1MCP Gateway  — http://127.0.0.1:3050
    4. Embedding     — circuit breaker state
    5. Disk usage    — data directory
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class ServiceStatus:
    """Status of a single service."""
    name: str
    healthy: bool = False
    latency_ms: float = 0.0
    detail: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "healthy": self.healthy,
            "latency_ms": round(self.latency_ms, 1),
            "detail": self.detail,
            "error": self.error,
        }


@dataclass
class HealthReport:
    """Complete health report for the memory server ecosystem."""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    services: list[ServiceStatus] = field(default_factory=list)
    overall_healthy: bool = False

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "overall_healthy": self.overall_healthy,
            "healthy_count": sum(1 for s in self.services if s.healthy),
            "total_count": len(self.services),
            "services": [s.to_dict() for s in self.services],
        }


# ── Individual Checkers ───────────────────────────────────────────

def _check_http(name: str, url: str, timeout: float = 3.0) -> ServiceStatus:
    """Generic HTTP health check."""
    import urllib.request
    import urllib.error

    status = ServiceStatus(name=name)
    start = time.monotonic()
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            elapsed = (time.monotonic() - start) * 1000
            status.healthy = True
            status.latency_ms = elapsed
            body = resp.read().decode("utf-8", errors="replace")[:200]
            try:
                data = json.loads(body)
                status.detail = json.dumps(data)[:150]
            except json.JSONDecodeError:
                status.detail = body[:150]
    except urllib.error.URLError as e:
        elapsed = (time.monotonic() - start) * 1000
        status.latency_ms = elapsed
        status.error = str(e.reason) if hasattr(e, "reason") else str(e)
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        status.latency_ms = elapsed
        status.error = f"{type(e).__name__}: {e}"
    return status


def check_qdrant(url: str = "http://127.0.0.1:6333") -> ServiceStatus:
    """Check Qdrant vector store health."""
    status = _check_http("qdrant", f"{url}/healthz")
    if status.healthy:
        # Also get collection count
        try:
            import urllib.request
            req = urllib.request.Request(f"{url}/collections", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read())
                collections = data.get("result", {}).get("collections", [])
                status.detail = f"{len(collections)} collections"
        except Exception:
            pass
    return status


def check_llama_server(url: str = "http://127.0.0.1:8081") -> ServiceStatus:
    """Check llama-server embedding daemon."""
    return _check_http("llama-server", f"{url}/health")


def check_gateway(url: str = "http://127.0.0.1:3050") -> ServiceStatus:
    """Check 1MCP gateway."""
    status = _check_http("gateway", url)
    
    # 1MCP returns 404 for / but IS healthy if it responds
    if not status.healthy and ("Not Found" in status.error or "Not Found" in status.detail):
        # It responded with 404 — that means the server IS running
        status.healthy = True
        status.detail = "Running (HTTP responding)"
        status.error = ""
    
    if not status.healthy and "Connection refused" in status.error:
        # Check if process is running (STDIO mode)
        import subprocess
        try:
            result = subprocess.run(
                ["pgrep", "-f", "1mcp serve"],
                capture_output=True, text=True, timeout=2,
            )
            if result.returncode == 0:
                status.healthy = True
                status.detail = "Process running (STDIO mode)"
                status.error = ""
        except Exception:
            pass
    return status


def check_embedding_pipeline() -> ServiceStatus:
    """Check embedding pipeline including circuit breaker."""
    status = ServiceStatus(name="embedding")
    try:
        from shared.embedding import get_cache_stats, get_embedding
        stats = get_cache_stats()
        cb = stats.get("circuit_breaker", {})
        status.detail = (
            f"cache={stats['size']}/{stats['maxsize']}, "
            f"hits={stats['hits']}, "
            f"breaker={cb.get('state', 'unknown')}"
        )
        if cb.get("state") == "open":
            status.healthy = False
            status.error = f"Circuit breaker OPEN ({cb.get('failure_count', 0)} failures)"
        else:
            status.healthy = True
    except Exception as e:
        status.error = str(e)
    return status


def check_disk_usage(base_dir: Optional[str] = None) -> ServiceStatus:
    """Check disk usage of data directory."""
    status = ServiceStatus(name="disk")
    try:
        if base_dir is None:
            base_dir = os.getenv("MEMORY_SERVER_DIR", ".")
        data_path = Path(base_dir) / "data"
        if data_path.exists():
            total_size = sum(f.stat().st_size for f in data_path.rglob("*") if f.is_file())
            size_mb = total_size / (1024 * 1024)
            status.healthy = size_mb < 5000  # Warn if > 5GB
            status.detail = f"{size_mb:.1f} MB in {data_path}"
            if not status.healthy:
                status.error = f"Data directory > 5GB ({size_mb:.0f} MB)"
        else:
            status.error = f"Data directory not found: {data_path}"
    except Exception as e:
        status.error = str(e)
    return status


def check_launchd() -> ServiceStatus:
    """Check launchd plist status."""
    status = ServiceStatus(name="launchd")
    import subprocess
    try:
        result = subprocess.run(
            ["launchctl", "list"],
            capture_output=True, text=True, timeout=5,
        )
        # Core services that must always be running
        core_services = [
            "com.memory-server.qdrant",
            "com.memory-server.llama-embedding",
            "com.memory-server.gateway",
        ]
        services = {}
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 3 and "memory-server" in parts[2]:
                pid = parts[0] if parts[0] != "-" else "not running"
                exit_code = parts[1]
                services[parts[2]] = {"pid": pid, "exit": exit_code}

        # Check only core services
        core_running = 0
        for svc_name in core_services:
            if svc_name in services and services[svc_name]["pid"] != "not running":
                core_running += 1
            elif svc_name in services and services[svc_name]["pid"] == "not running":
                status.error += f"{svc_name} not running; "

        total = len(services)
        status.healthy = core_running == len(core_services)
        status.detail = f"{core_running}/{len(core_services)} core services running ({total} total)"

        if not services:
            status.error = "No memory-server launchd services found"
    except Exception as e:
        status.error = str(e)
    return status


# ── Main Health Check ──────────────────────────────────────────────

def run_health_check(qdrant_url: str | None = None,
                     llama_url: str | None = None,
                     gateway_url: str | None = None,
                     base_dir: str | None = None) -> HealthReport:
    """Run all health checks and return a report."""
    qdrant_url = qdrant_url or os.getenv("QDRANT_URL", "http://127.0.0.1:6333")
    llama_url = llama_url or os.getenv("LLAMA_SERVER_URL", "http://127.0.0.1:8081")
    gateway_url = gateway_url or "http://127.0.0.1:3050"
    base_dir = base_dir or os.getenv("MEMORY_SERVER_DIR")

    report = HealthReport()
    report.services = [
        check_qdrant(qdrant_url),
        check_llama_server(llama_url),
        check_gateway(gateway_url),
        check_embedding_pipeline(),
        check_disk_usage(base_dir),
        check_launchd(),
    ]
    report.overall_healthy = all(s.healthy for s in report.services)
    return report


def format_report(report: HealthReport, use_color: bool = True) -> str:
    """Format health report as a human-readable string."""
    lines = []
    g = "\033[32m" if use_color else ""
    r = "\033[31m" if use_color else ""
    y = "\033[33m" if use_color else ""
    b = "\033[1m" if use_color else ""
    x = "\033[0m" if use_color else ""

    status_icon = f"{g}✅{x}" if report.overall_healthy else f"{r}❌{x}"
    healthy_count = sum(1 for s in report.services if s.healthy)
    total = len(report.services)

    lines.append(f"\n{b}🏥 MCP Memory Server Health Check{x}")
    lines.append(f"   {status_icon} {healthy_count}/{total} services healthy")
    lines.append(f"   📅 {report.timestamp}\n")

    for svc in report.services:
        icon = f"{g}✅{x}" if svc.healthy else f"{r}❌{x}"
        latency = f"{svc.latency_ms:.0f}ms" if svc.latency_ms > 0 else ""
        detail = f" — {svc.detail}" if svc.detail else ""
        error = f" ({r}{svc.error}{x})" if svc.error else ""

        lines.append(f"  {icon} {svc.name:<15} {latency:>8} {detail}{error}")

    lines.append("")
    return "\n".join(lines)


# ── CLI ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="MCP Memory Server Health Check")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--watch", type=int, metavar="INTERVAL",
                        help="Continuous monitoring (seconds)")
    parser.add_argument("--qdrant-url", default=None)
    parser.add_argument("--llama-url", default=None)
    parser.add_argument("--gateway-url", default=None)
    args = parser.parse_args()

    def _run():
        report = run_health_check(
            qdrant_url=args.qdrant_url,
            llama_url=args.llama_url,
            gateway_url=args.gateway_url,
        )
        if args.json:
            print(json.dumps(report.to_dict(), indent=2))
        else:
            print(format_report(report))
        return report.overall_healthy

    if args.watch:
        while True:
            _run()
            print(f"--- next check in {args.watch}s ---\n")
            time.sleep(args.watch)
    else:
        healthy = _run()
        sys.exit(0 if healthy else 1)
