"""M3 sparse fusion tests — RET-05 (sparse read path) + RET-07 (determinism).

The boost formula `final = dense + w*s*(1-dense)` is monotonic: sparse can
only improve a score, never shrink it — preserving score_threshold semantics
from M2 exactly when sparse contributes nothing.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from shared.memory_db import MemoryDB


def _tok_id(token: str) -> int:
    """Stable 32-bit token id — same scheme as embedding.bm25_tokenize (M3 fix)."""
    return int.from_bytes(hashlib.sha256(token.encode("utf-8")).digest()[:4], "big")


def _sparse(tokens: dict[str, float]) -> dict:
    return {"indices": [_tok_id(t) for t in tokens], "values": list(tokens.values())}


def _q(text: str) -> dict:
    return _sparse({t: 1.0 for t in text.lower().split()})


def _vec(seed: float, dim: int = 8) -> list[float]:
    v = [seed] * dim
    n = sum(x * x for x in v) ** 0.5
    return [x / n for x in v]


def _dir(vals: list[float]) -> list[float]:
    n = sum(x * x for x in vals) ** 0.5
    return [x / n for x in vals]


@pytest.fixture()
def db(tmp_path):
    d = MemoryDB(str(tmp_path / "memory.db"), collection="L0_L4_memory", embedding_dim=8)
    d._ensure_schema()
    yield d
    d._conn.close()


@pytest.mark.unit
async def test_lexical_boost_ranks_token_match_first(db):
    # equal DENSE scores (same vector, <1.0 vs query) -> sparse decides
    qv = _vec(1.0)
    rowv = _dir([1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3])  # different direction: cosine(q,row) < 1
    await db.upsert("no-tokens", rowv, {"content": "totally unrelated words"})
    await db.upsert("with-tokens", rowv, {"content": "postgres indexing strategy"})
    db._conn.execute(
        "UPDATE points SET sparse_json=? WHERE id='with-tokens'",
        (json.dumps(_sparse({"postgres": 1.0, "indexing": 2.0, "strategy": 1.0})),),
    )
    db._conn.commit()
    hits = await db.search(qv, limit=5, score_threshold=0.0,
                           filter={"must": [{"key": "agent_scope", "match": {"value": "shared"}}]},
                           sparse_query=_q("postgres indexing strategy"))
    assert hits[0]["id"] == "with-tokens"
    assert hits[0]["score_source"] == "dense+sparse"
    assert hits[0]["score"] > hits[1]["score"]


@pytest.mark.unit
async def test_sparse_zero_preserves_dense_score_exactly(db):
    await db.upsert("a", _vec(0.5), {"content": "some content"})
    base = await db.search(_vec(0.5), limit=5, score_threshold=-1.0,
                           filter={"must": [{"key": "agent_scope", "match": {"value": "shared"}}]})
    fused = await db.search(_vec(0.5), limit=5, score_threshold=-1.0,
                            filter={"must": [{"key": "agent_scope", "match": {"value": "shared"}}]},
                            sparse_query=_q("words absent from content"))
    assert fused[0]["score"] == base[0]["score"]          # boost formula: no shrink
    assert fused[0]["score_source"] == "dense"            # no "+sparse" tag


@pytest.mark.unit
async def test_boost_monotonic_and_capped(db):
    await db.upsert("a", _vec(0.4), {"content": "x"})
    db._conn.execute(
        "UPDATE points SET sparse_json=? WHERE id='a'",
        (json.dumps(_sparse({"x": 9.0})),),
    )
    db._conn.commit()
    base = await db.search(_vec(0.4), limit=1, score_threshold=-1.0,
                           filter={"must": [{"key": "agent_scope", "match": {"value": "shared"}}]})
    fused = await db.search(_vec(0.4), limit=1, score_threshold=-1.0,
                            filter={"must": [{"key": "agent_scope", "match": {"value": "shared"}}]},
                            sparse_query=_q("x"), sparse_weight=0.9)
    assert fused[0]["score"] > base[0]["score"]           # improves
    assert fused[0]["score"] <= 1.0 + 1e-9                # capped


@pytest.mark.unit
async def test_hash_row_gets_sparse_boost(db):
    await db.upsert("null-vec", None, {"content": "kubernetes ingress rules"})
    db._conn.execute(
        "UPDATE points SET sparse_json=? WHERE id='null-vec'",
        (json.dumps(_sparse({"kubernetes": 2.0, "ingress": 1.0})),),
    )
    db._conn.commit()
    hits = await db.search(None, limit=5, score_threshold=-1.0,
                           filter={"must": [{"key": "agent_scope", "match": {"value": "shared"}}]},
                           sparse_query=_q("kubernetes ingress"))
    assert hits[0]["score_source"] == "hash+sparse"
    assert hits[0]["score"] > 0.0


@pytest.mark.unit
async def test_corrupt_stored_sparse_json_degrades_to_dense(db):
    await db.upsert("bad-sparse", _vec(0.7), {"content": "content here"})
    db._conn.execute("UPDATE points SET sparse_json='{not json' WHERE id='bad-sparse'")
    db._conn.commit()
    hits = await db.search(_vec(0.7), limit=5, score_threshold=-1.0,
                           filter={"must": [{"key": "agent_scope", "match": {"value": "shared"}}]},
                           sparse_query=_q("content here tokens"))
    assert hits[0]["score_source"] == "dense"             # degraded, not crashed
    assert hits[0]["id"] == "bad-sparse"


@pytest.mark.unit
@pytest.mark.parametrize(
    "bad",
    [
        "not-a-dict",
        {"indices": "x", "values": []},
        {"indices": [1, 2], "values": [1.0]},
        {"indices": ["a"], "values": [1.0]},
        {"indices": [1], "values": ["b"]},
        {"indices": [1], "values": [None]},
    ],
)
async def test_malformed_sparse_query_fails_closed(db, bad):
    await db.upsert("a", _vec(1.0), {"content": "x"})
    with pytest.raises(ValueError):
        await db.search(_vec(1.0), filter={"must": [{"key": "agent_scope", "match": {"value": "shared"}}]},
                        sparse_query=bad)


@pytest.mark.unit
async def test_tie_break_is_deterministic(db):
    v = _vec(0.6)
    for rid in ["c-row", "a-row", "b-row"]:
        await db.upsert(rid, v, {"content": "same", "row": rid})
    runs = [
        await db.search(v, limit=10, score_threshold=0.0,
                        filter={"must": [{"key": "agent_scope", "match": {"value": "shared"}}]})
        for _ in range(2)
    ]
    orders = [[h["id"] for h in run] for run in runs]
    assert orders[0] == orders[1]                          # reproducible
    tied = [h["id"] for h in runs[0]]
    assert tied == sorted(tied)                            # id asc within ties


@pytest.mark.unit
async def test_isolation_unchanged_by_fusion(db, monkeypatch):
    """Fusion runs on engine-filtered candidates only (ISO-05 holds)."""
    await db.upsert("u1-row", _vec(1.0), {"content": "mine", "user_id": "u1"})
    await db.upsert("u2-row", _vec(1.0), {"content": "theirs", "user_id": "u2"})
    db._conn.execute(
        "UPDATE points SET sparse_json=? WHERE id='u2-row'",
        (json.dumps(_sparse({"mine": 5.0})),),
    )
    db._conn.commit()

    scored_ids = []
    orig = MemoryDB._score_candidates

    def spy(self, rows, qv):
        scored_ids.extend(r["id"] for r in rows)
        return orig(self, rows, qv)

    monkeypatch.setattr(MemoryDB, "_score_candidates", spy)
    await db.search(_vec(1.0), limit=10, score_threshold=0.0,
                    filter={"must": [{"key": "user_id", "match": {"value": "u1"}}]},
                    sparse_query=_q("mine"))
    assert scored_ids == ["u1-row"]                        # u2 never fetched, sparse or not
