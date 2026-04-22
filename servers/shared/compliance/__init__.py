"""Compliance Verifier — checks LLM output against project rules.

Two-level verification:
  1. Deterministic (regex/AST) — fast, 100% reliable for code rules
  2. Semantic (small LLM) — catches contradictions, intent violations

Usage:
    from shared.compliance import verify_compliance

    result = await verify_compliance(
        llm_output="class User(BaseModel):\n    class Config:\n        use_enum_values = True",
        rules=PROJECT_RULES,
        session_context={"open_files": ["src/models/user.py"]},
    )
    if not result.compliant:
        print(f"Violations: {result.violations}")
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# ── Rule Definitions ──────────────────────────────────────────────

@dataclass
class ProjectRule:
    """A single project rule that can be verified."""
    id: str
    description: str
    severity: str            # "critical" | "high" | "medium" | "low"
    # Deterministic checks (regex patterns that should NOT match)
    forbidden_patterns: list[str] = field(default_factory=list)
    # Required patterns (should match)
    required_patterns: list[str] = field(default_factory=list)
    # Semantic check prompt (for small LLM)
    semantic_prompt: str | None = None


# Default project rules — extend as needed
DEFAULT_RULES: list[ProjectRule] = [
    ProjectRule(
        id="PYDANTIC_V2_CONFIG",
        description="Never use `class Config` in Pydantic models — use `model_config = ConfigDict(...)`",
        severity="high",
        forbidden_patterns=[
            r"class\s+Config\s*:",
        ],
        required_patterns=[],
        semantic_prompt=None,
    ),

    ProjectRule(
        id="NO_SECRETS_IN_CODE",
        description="Never expose API keys, tokens, passwords, or secrets in code or logs",
        severity="critical",
        forbidden_patterns=[
            r"(?:api_?key|apikey|secret_?key|password|passwd|token)\s*=\s*[\"'][^\"']{8,}[\"']",
            r"(?:AWS_SECRET|PRIVATE_KEY|DATABASE_URL)\s*=",
        ],
        required_patterns=[],
        semantic_prompt=None,
    ),

    ProjectRule(
        id="DATETIME_UTC",
        description="Use `datetime.now(timezone.utc)` instead of deprecated `datetime.utcnow()`",
        severity="medium",
        forbidden_patterns=[
            r"datetime\.utcnow\(\)",
        ],
        required_patterns=[],
        semantic_prompt=None,
    ),

    ProjectRule(
        id="NO_BARE_EXCEPT",
        description="Never use bare `except:` — always specify the exception type",
        severity="medium",
        forbidden_patterns=[
            r"except\s*:",
        ],
        required_patterns=[],
        semantic_prompt=None,
    ),

    ProjectRule(
        id="NO_EVAL",
        description="Never use eval(), exec(), or subprocess with shell=True on user input",
        severity="critical",
        forbidden_patterns=[
            r"\beval\s*\(",
            r"\bexec\s*\(",
            r"subprocess\..*shell\s*=\s*True",
        ],
        required_patterns=[],
        semantic_prompt=None,
    ),

    ProjectRule(
        id="INPUT_VALIDATION",
        description="All user input must be validated before use",
        severity="high",
        forbidden_patterns=[],
        required_patterns=[],
        semantic_prompt=(
            "Check if the following code validates all user input before using it. "
            "Look for: type checks, length limits, allowed values, sanitization. "
            "If user input is used directly without any validation, it's a VIOLATION."
        ),
    ),
]


# ── Verification Result ───────────────────────────────────────────

@dataclass
class Violation:
    """A single rule violation."""
    rule_id: str
    rule_description: str
    severity: str
    detail: str            # What was found and where
    line_number: int | None = None
    matched_text: str | None = None


@dataclass
class ComplianceResult:
    """Result of compliance verification."""
    compliant: bool
    violations: list[Violation] = field(default_factory=list)
    checked_rules: list[str] = field(default_factory=list)
    semantic_checks: int = 0
    deterministic_checks: int = 0


# ── Level 1: Deterministic Verification ───────────────────────────

def verify_deterministic(
    code: str,
    rules: list[ProjectRule] | None = None,
) -> list[Violation]:
    """Check code against deterministic rules (regex/AST).

    Returns list of violations. Empty list = all rules passed.
    """
    rules = rules or DEFAULT_RULES
    violations: list[Violation] = []

    for rule in rules:
        # Check forbidden patterns
        for pattern in rule.forbidden_patterns:
            matches = list(re.finditer(pattern, code, re.MULTILINE))
            for match in matches:
                # Find line number
                line_num = code[:match.start()].count('\n') + 1
                violations.append(Violation(
                    rule_id=rule.id,
                    rule_description=rule.description,
                    severity=rule.severity,
                    detail=f"Found forbidden pattern: {pattern!r}",
                    line_number=line_num,
                    matched_text=match.group()[:100],
                ))

        # Check required patterns
        if rule.required_patterns:
            all_found = True
            for pattern in rule.required_patterns:
                if not re.search(pattern, code, re.MULTILINE):
                    all_found = False
                    violations.append(Violation(
                        rule_id=rule.id,
                        rule_description=rule.description,
                        severity=rule.severity,
                        detail=f"Missing required pattern: {pattern!r}",
                    ))
                    break

    return violations


# ── Level 2: Semantic Verification ────────────────────────────────

async def verify_semantic(
    code: str,
    rules: list[ProjectRule] | None = None,
    context: dict[str, Any] | None = None,
) -> list[Violation]:
    """Check code against semantic rules using small LLM.

    Returns list of violations. Empty list = all rules passed.
    """
    rules = rules or DEFAULT_RULES
    violations: list[Violation] = []

    # Find rules that need semantic checking
    semantic_rules = [r for r in rules if r.semantic_prompt]
    if not semantic_rules:
        return violations

    from ..llm import get_small_llm

    try:
        llm = get_small_llm()
        if not llm.is_available():
            return violations  # Can't do semantic checks without LLM
    except Exception:
        return violations  # No small LLM configured

    for rule in semantic_rules:
        prompt = (
            f"You are a code compliance auditor. Check if the following code violates this rule:\n\n"
            f"RULE: {rule.description}\n\n"
            f"CHECK: {rule.semantic_prompt}\n\n"
            f"CODE:\n{code}\n\n"
            f"Respond with ONLY 'COMPLIANT' or 'VIOLATION: <brief reason>'."
        )

        try:
            response = llm.ask(prompt, max_tokens=128, temperature=0.0)
            if response.strip().upper().startswith("VIOLATION"):
                reason = response.strip().replace("VIOLATION:", "").strip()
                violations.append(Violation(
                    rule_id=rule.id,
                    rule_description=rule.description,
                    severity=rule.severity,
                    detail=f"Semantic violation: {reason}",
                ))
        except Exception:
            pass  # Semantic check failure = not a violation, just skip

    return violations


# ── Public API ────────────────────────────────────────────────────

async def verify_compliance(
    code: str,
    rules: list[ProjectRule] | None = None,
    session_context: dict[str, Any] | None = None,
) -> ComplianceResult:
    """Full compliance check: deterministic + semantic.

    Args:
        code: The code/output to verify.
        rules: Custom rules to check. Uses DEFAULT_RULES if None.
        session_context: Additional context (open files, etc.)

    Returns:
        ComplianceResult with all violations found.
    """
    rules = rules or DEFAULT_RULES

    # Level 1: Deterministic
    det_violations = verify_deterministic(code, rules)

    # Level 2: Semantic
    sem_violations = await verify_semantic(code, rules, session_context)

    all_violations = det_violations + sem_violations
    # Deduplicate by rule_id
    seen: set[str] = set()
    unique_violations = []
    for v in all_violations:
        if v.rule_id not in seen:
            seen.add(v.rule_id)
            unique_violations.append(v)

    det_rules_checked = len([r for r in rules if r.forbidden_patterns or r.required_patterns])
    sem_rules_checked = len([r for r in rules if r.semantic_prompt])

    return ComplianceResult(
        compliant=len(unique_violations) == 0,
        violations=unique_violations,
        checked_rules=[r.id for r in rules],
        semantic_checks=sem_rules_checked,
        deterministic_checks=det_rules_checked,
    )


def add_rule(rule: ProjectRule) -> None:
    """Add a custom rule to the default set."""
    DEFAULT_RULES.append(rule)


def remove_rule(rule_id: str) -> None:
    """Remove a rule by ID."""
    global DEFAULT_RULES
    DEFAULT_RULES = [r for r in DEFAULT_RULES if r.id != rule_id]
