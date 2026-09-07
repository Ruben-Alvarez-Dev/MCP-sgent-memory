# Tasks: M0 — Baseline freeze

## 1. Scaffold
- [ ] 1.1 `openspec/config.yaml` + base specs (retrieval/isolation/consolidation/storage) committed.
- [ ] 1.2 `tests/{unit,contract,integration,adversarial,eval,e2e}/` skeleton + pytest markers in `pyproject.toml` (`pytest --markers` lists them).

## 2. Evidence freeze
- [ ] 2.1 Run `pytest tests/core -q` → `evidence/suite-core.txt` (record failures as KNOWN-BUGs, do not fix).
- [ ] 2.2 Run scope tests `-v` → `evidence/suite-scope.txt`.
- [ ] 2.3 Service probes → `evidence/latency.json` (embed/Qdrant/:8081).
- [ ] 2.4 Leak inventory → `evidence/leaks.md` with file:line per L-R1/L-D1/L-F1/L-C1/L-V1.
- [ ] 2.5 Known bugs file → `evidence/known-bugs.md` (KNOWN-BUG-001, KNOWN-BUG-002).
- [ ] 2.6 Eval-40 query list → `evidence/eval-40.yaml` (no judgments yet).

## 3. Gate
- [ ] 3.1 Fill `GATE_0.md` (checks + human checklist + signatures) and record GO/NO-GO.
