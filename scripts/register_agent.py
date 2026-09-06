#!/usr/bin/env python3
"""Agent identity registry CLI (M4, ISO-13).

    register <agent_id>          Create/rotate credential; prints the token ONCE.
    verify   <agent_id> <token>  Check a credential pair (exit 0/1).
    list                         List registered agents (no secrets).

Example — wire an agent (harness mcp.json env block):
    MEMORY_AGENT_ID=director-1
    MEMORY_AGENT_TOKEN=<printed token>
    MEMORY_IDENTITY_MODE=strict
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "src"))

from shared.identity import AgentRegistry, IdentityError  # noqa: E402
from shared.scope import ScopeError  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_reg = sub.add_parser("register", help="create/rotate an agent credential")
    p_reg.add_argument("agent_id")

    p_ver = sub.add_parser("verify", help="verify an id+token pair")
    p_ver.add_argument("agent_id")
    p_ver.add_argument("token")

    sub.add_parser("list", help="list registered agents")

    args = ap.parse_args()
    reg = AgentRegistry()

    try:
        if args.cmd == "register":
            token = reg.register(args.agent_id)
            print(f"✅ agent {args.agent_id!r} registered.")
            print(f"TOKEN (shown ONCE — store it in the agent harness env now):\n{token}")
            print("\nmcp.json env block:")
            print(f'  "MEMORY_AGENT_ID": "{args.agent_id}",')
            print(f'  "MEMORY_AGENT_TOKEN": "{token}",')
            print('  "MEMORY_IDENTITY_MODE": "strict"')
            return 0
        if args.cmd == "verify":
            ok = reg.verify(args.agent_id, args.token)
            print("OK" if ok else "MISMATCH")
            return 0 if ok else 1
        if args.cmd == "list":
            agents = reg.list_agents()
            if not agents:
                print("(registry empty)")
            for aid, meta in agents.items():
                print(f"{aid}  created={meta.get('created_at', '?')}")
            return 0
    except ScopeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    except IdentityError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
