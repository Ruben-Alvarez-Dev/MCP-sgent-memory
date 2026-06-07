#!/bin/bash
# reembed-pending.sh — Daily corpus self-healing for embedding failures.
# Scans L1 for zero-vector points (the F-11 contamination signature) and
# re-embeds them via bge-m3. Long contents are truncated to 600 chars to
# stay inside the embedding server's batch token limit (the cause of the
# 13 "toxic" failures found in the audit). Scheduled: launchd 04:30 daily.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

"$PROJECT_ROOT/.venv/bin/python3" - <<'EOF'
import json, urllib.request, time

def post(url, body, method="POST"):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method=method)
    return json.load(urllib.request.urlopen(req, timeout=60))

zeros, offset = [], None
while True:
    body = {"filter": {"must": [{"key": "layer", "match": {"value": 1}}]},
            "limit": 256, "with_payload": ["content"], "with_vector": True}
    if offset:
        body["offset"] = offset
    res = post("http://127.0.0.1:6333/collections/L0_L4_memory/points/scroll", body)["result"]
    for p in res["points"]:
        v = p.get("vector")
        if isinstance(v, dict):
            v = v.get("") or next((x for x in v.values() if isinstance(x, list)), None)
        if v is not None and all(x == 0.0 for x in v):
            zeros.append({"id": p["id"], "content": str((p.get("payload") or {}).get("content", ""))})
    offset = res.get("next_page_offset")
    if not offset:
        break

work = [z for z in zeros if len(z["content"].strip()) >= 10]
print(f"[reembed] zero-vectors: {len(zeros)} | healable: {len(work)}")
done = fail = 0
for z in work:
    text = z["content"][:600]   # truncate: avoids batch/token overflow (audit lesson)
    try:
        e = post("http://127.0.0.1:8081/v1/embeddings", {"input": text, "model": "bge-m3"})["data"][0]["embedding"]
        if any(x != 0 for x in e):
            post("http://127.0.0.1:6333/collections/L0_L4_memory/points/vectors?wait=true",
                 {"points": [{"id": z["id"], "vector": e}]}, method="PUT")
            done += 1
    except Exception:
        fail += 1
    time.sleep(0.05)
print(f"[reembed] healed={done} failed={fail}")
EOF
