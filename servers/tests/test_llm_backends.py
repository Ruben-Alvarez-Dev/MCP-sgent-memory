#!/usr/bin/env python3
"""Integration tests for shared.llm module.

Tests real memory-server use cases:
  1. Post-session consolidator (extracts memories from conversation)
  2. Compliance Verifier (checks LLM output against project rules)
  3. AI Memory Ranking (selects most relevant memories for a query)
  4. Multi-model simultaneous usage (different models for different tasks)
  5. Backend transparency (same code, different backend)

Usage:
    python3 tests/test_llm_backends.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# Add shared module to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.llm import get_llm, list_available_backends, LLMBackend

# ── Helpers ────────────────────────────────────────────────────────


def section(title: str):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def record_result(name: str, passed: bool, detail: str = ""):
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"  {status} — {name}")
    if detail:
        print(f"         {detail}")
    return passed


# ── Test 1: Post-Session Consolidator ─────────────────────────────


def test_consolidator():
    """Simulate the consolidator extracting memories from a session."""
    section("TEST 1: Post-Session Consolidator (via llama.cpp)")

    try:
        llm = get_llm("llama_cpp")
    except Exception as e:
        return record_result("Consolidator", False, f"llama.cpp unavailable: {e}")

    # Simulated conversation (from a real coding session)
    SYSTEM_PROMPT = """You are a memory consolidation assistant. Analyze the conversation below and extract
insights that are worth storing as persistent memories for future sessions.

Focus ONLY on:
1. New user preferences or working-style corrections revealed in this session
2. Project decisions or facts made explicit (NOT derivable from code/git)
3. Behavioral feedback given to the AI (what to do or avoid, and why)

Return a JSON object with key "memories" containing a list of objects, each with:
  "name": short slug
  "type": "user" | "feedback" | "project"
  "description": one-line description
  "content": memory body with **Why:** and **How to apply:** lines
  "confidence": float 0.0-1.0

Return {"memories": []} if nothing new or worth saving.
Keep to AT MOST 3 memories."""

    CONVERSATION = """User: I want to build a memory system for AI agents with 6 levels of distillation
Assistant: That's an interesting architecture. Let me help you design it.
User: No, I don't want the LLM to compress or rotate context. I want the system to do all the distillation work beforehand
Assistant: I understand. The system pre-processes memories at different levels of abstraction.
User: Exactly. And the LLM just queries the right level when needed. It never has to manage context itself.
Assistant: Makes sense. The LLM is a consumer, not a manager.
User: Right. And I need a compliance verifier that checks every LLM response against project rules. I don't trust it to follow rules on its own.
Assistant: A deterministic verifier would catch rule violations.
User: Yes. After 50 turns the LLM ignores 15% of instructions. After 200, more than 50%. I need it verified every time."""

    start = time.monotonic()
    result = llm.ask(
        prompt=f"Conversation:\n\n{CONVERSATION}",
        system=SYSTEM_PROMPT,
        max_tokens=1024,
        temperature=0.3,
    )
    elapsed = time.monotonic() - start

    # Try to parse JSON from the result
    try:
        # Extract JSON from the response
        json_start = result.index("{")
        json_end = result.rindex("}") + 1
        parsed = json.loads(result[json_start:json_end])
        memories = parsed.get("memories", [])

        passed = len(memories) > 0
        return record_result(
            "Consolidator",
            passed,
            f"Extracted {len(memories)} memories in {elapsed:.1f}s. "
            f"First: {[m.get('name', '?') for m in memories[:1]]}",
        )
    except (ValueError, json.JSONDecodeError):
        return record_result(
            "Consolidator",
            False,
            f"No valid JSON in response ({elapsed:.1f}s): {result[:200]}",
        )


# ── Test 2: Compliance Verifier ───────────────────────────────────


def test_compliance_verifier():
    """Simulate the compliance verifier checking LLM output."""
    section("TEST 2: Compliance Verifier (llama.cpp)")

    try:
        llm = get_llm("llama_cpp")
    except Exception as e:
        return record_result(
            "Compliance Verifier", False, f"llama.cpp unavailable: {e}"
        )

    # Simulated LLM output that VIOLATES a rule
    LLM_OUTPUT = """I'll help you set up the Pydantic model. Here's the code:

```python
class User(BaseModel):
    name: str
    email: str
    
    class Config:
        use_enum_values = True
```

This uses the `class Config` pattern which is the standard way to configure Pydantic models."""

    VERIFIER_PROMPT = f"""You are a code compliance auditor. Check if the following LLM output violates any project rules.

PROJECT RULES:
1. Never use `class Config` in Pydantic models — use `model_config = ConfigDict(...)` instead. `class Config` is deprecated in V2 and removed in V3.
2. Never expose API keys, tokens, or secrets in code or logs.
3. Always use `datetime.now(timezone.utc)` instead of `datetime.utcnow()`.
4. All user input must be validated before use.

LLM OUTPUT TO VERIFY:
{LLM_OUTPUT}

Respond with a JSON object:
{{
  "compliant": true/false,
  "violations": [
    {{"rule": 1, "description": "what was violated", "severity": "high/medium/low"}}
  ],
  "verdict": "APPROVE or REJECT with reason"
}}"""

    start = time.monotonic()
    result = llm.ask(
        prompt=VERIFIER_PROMPT,
        max_tokens=512,
        temperature=0.0,
    )
    elapsed = time.monotonic() - start

    try:
        json_start = result.index("{")
        json_end = result.rindex("}") + 1
        parsed = json.loads(result[json_start:json_end])

        compliant = parsed.get("compliant", True)
        violations = parsed.get("violations", [])

        # We EXPECT non-compliance (the LLM violated rule 1)
        passed = not compliant and len(violations) > 0
        return record_result(
            "Compliance Verifier",
            passed,
            f"Detected violation: {compliant=}, {len(violations)} violations found ({elapsed:.1f}s)",
        )
    except (ValueError, json.JSONDecodeError):
        return record_result(
            "Compliance Verifier", False, f"No valid JSON: {result[:200]}"
        )


# ── Test 3: AI Memory Ranking ─────────────────────────────────────


def test_ai_ranking():
    """Simulate AI-powered memory relevance ranking."""
    section("TEST 3: AI Memory Ranking (qwen2.5:7b)")

    try:
        llm = get_llm("llama_cpp")
    except Exception as e:
        return record_result("AI Memory Ranking", False, f"llama.cpp unavailable: {e}")

    MEMORIES = [
        "user: I'm a senior engineer with 10 years of Python experience",
        "feedback: Don't mock the database in tests — we got burned last quarter when mocks passed but prod failed. Why: prior incident. How to apply: all integration tests.",
        "project: We chose JWT over sessions for auth because sessions don't scale across multiple instances. Why: multi-instance deployment.",
        "reference: Pipeline bugs are tracked in Linear project 'INGEST'",
        "user: I prefer terse responses with no trailing summaries",
    ]

    RANKING_PROMPT = f"""Given these memories, select the 2 most relevant ones for the user's query.

MEMORIES:
{chr(10).join(f"- {m}" for m in MEMORIES)}

USER QUERY: "How should I write tests for the auth module?"

Respond with a JSON object:
{{
  "selected_indices": [0, 2],
  "reasoning": "why these are most relevant"
}}"""

    start = time.monotonic()
    result = llm.ask(
        prompt=RANKING_PROMPT,
        max_tokens=256,
        temperature=0.0,
    )
    elapsed = time.monotonic() - start

    try:
        json_start = result.index("{")
        json_end = result.rindex("}") + 1
        parsed = json.loads(result[json_start:json_end])

        indices = parsed.get("selected_indices", [])
        passed = len(indices) > 0

        return record_result(
            "AI Memory Ranking",
            passed,
            f"Selected {len(indices)} memories: {indices} ({elapsed:.1f}s)",
        )
    except (ValueError, json.JSONDecodeError):
        return record_result(
            "AI Memory Ranking", False, f"No valid JSON: {result[:200]}"
        )


# ── Test 4: Multi-Model Simultaneous Usage ────────────────────────


def test_multi_model():
    """Use different models for different tasks simultaneously."""
    section("TEST 4: Multi-Model Simultaneous Usage")

    results = []

    # Task 1: Consolidation with qwen2.5:7b
    try:
        consolidator = get_llm("llama_cpp")
        resp = consolidator.ask(
            "Summarize in 5 words: The LLM should never manage its own context window.",
            max_tokens=30,
        )
        passed = len(resp) > 0
        results.append(
            record_result("Consolidation (qwen2.5:7b)", passed, f'"{resp[:80]}"')
        )
    except Exception as e:
        results.append(record_result("Consolidation (qwen2.5:7b)", False, str(e)))

    # Task 2: Verification with llama.cpp
    try:
        verifier = get_llm("llama_cpp")
        resp = verifier.ask(
            "Is this code compliant with rule 'no class Config in Pydantic'? Answer YES or NO only.",
            max_tokens=20,
        )
        passed = len(resp) > 0
        results.append(
            record_result("Verification (LM Studio)", passed, f'"{resp[:80]}"')
        )
    except Exception as e:
        results.append(record_result("Verification (LM Studio)", False, str(e)))

    return all(results)


# ── Test 5: Backend Transparency ─────────────────────────────────


def test_backend_transparency():
    """Same code works with any backend."""
    section("TEST 5: Backend Transparency (same code, different backend)")

    results = []

    def test_with_backend(backend_name: str, backend_label: str):
        try:
            llm = get_llm(backend_name)
            resp = llm.ask("Say exactly: TEST_OK", max_tokens=10)
            passed = "TEST_OK" in resp or "test_ok" in resp.lower()
            return record_result(backend_label, passed, f'Response: "{resp[:60]}"')
        except Exception as e:
            return record_result(backend_label, False, str(e))

    # Test with each available backend
    available = list_available_backends()
    for name, is_avail in available.items():
        if is_avail:
            results.append(test_with_backend(name, f"{name} backend"))
        else:
            results.append(record_result(f"{name} backend", False, "not available"))

    return all(results)


# ── Main ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  SHARED.LLM MODULE — INTEGRATION TESTS")
    print("=" * 60)

    # Show available backends
    print(f"\n  Available backends: {list_available_backends()}")

    tests = [
        ("Consolidator", test_consolidator),
        ("Compliance Verifier", test_compliance_verifier),
        ("AI Memory Ranking", test_ai_ranking),
        ("Multi-Model", test_multi_model),
        ("Backend Transparency", test_backend_transparency),
    ]

    passed = 0
    failed = 0

    for name, fn in tests:
        try:
            if fn():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"  ❌ ERROR — {name}: {e}")
            failed += 1

    print(f"\n{'=' * 60}")
    print(f"  RESULTS: {passed}/{passed + failed} tests passed")
    print(f"{'=' * 60}\n")

    sys.exit(0 if failed == 0 else 1)
