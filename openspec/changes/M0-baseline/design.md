# Design: M0 — Baseline freeze

## What gets built
No product code. Artifacts only: `openspec/` tree, test skeleton, evidence files.

## Test skeleton layout
```
tests/
  unit/            # pure core, no I/O            marker: @pytest.mark.unit
  contract/        # StorageBackend ABC, schemas   marker: contract
  integration/     # real memory.db (M2+)          marker: integration
  adversarial/     # security matrix, fuzz, faults marker: nightly + isolation
  eval/            # eval-40 + parity scripts      marker: nightly
  e2e/             # harness simulators            marker: nightly
  core/ (legacy)   # kept until M6 cutover
  app/  (legacy)   # archived in M2 (Qdrant-bound) → tests/app/_archive_qdrant/
```
`pyproject.toml [tool.pytest.ini_options]`: add markers
`unit, contract, integration, nightly, isolation, req`.

## Baseline evidence to freeze (`evidence/`)
- `suite-core.txt`: full `pytest tests/core -q` output + durations.
- `suite-scope.txt`: `test_agent_scope_qdrant.py -v` output.
- `latency.json`: embed p50 (measured 0.85s CPU), Qdrant healthz, :8081 (expected DOWN).
- `leaks.md`: L-R1/L-D1/L-F1/L-C1/L-V1 re-confirmed with file:line.
- `known-bugs.md`: KNOWN-BUG-001 (`tests/app/conftest.py` expects `:8081`, `.env` runs `:8091`); KNOWN-BUG-002 (RET-06, L5 hard-fails without embeddings).
- `eval-40.yaml`: 40 queries (20 ES/20 EN across 5 intent classes) + metadata, judgments TBD in M3.

## Failure modes of this mission
- Services down during probing → record DOWN honestly, do not fake numbers.
- `tests/core` failures → recorded as baseline (a red baseline is still a baseline),
  each failure filed as KNOWN-BUG with ID.
- Empty Qdrant (2 points) → recall baseline is degenerate by construction; the
  honest baseline is latency + suite + leaks, and M3 builds a fixture corpus for
  the real parity eval. This deviation from the QA-architect draft is deliberate
  and recorded here.

## Open questions (resolved)
- Q: Full eval-40 with judgments now? A: No — judgments require the frozen fixture
  corpus (M3). M0 freezes the query list only. Deviation accepted by architect.
