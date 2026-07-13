"""Contract tests for the proposed Jart Memory foundation.

Every fixture in this module is deterministic, sanitized, and TEST-ONLY. The
values are not production identities, memory, credentials, or endpoints.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIRECTORY = REPOSITORY_ROOT / "contracts" / "jsonschema"
EXPECTED_SCHEMAS = {
    "common.schema.json",
    "identity-context.schema.json",
    "session.schema.json",
    "memory-event.schema.json",
    "memory-record.schema.json",
    "memory-grant.schema.json",
    "promotion-case.schema.json",
}

TEST_ONLY_UUIDS = {name: f"018f0d6e-7a69-7{name:02x}0-8000-{name:012x}" for name in range(1, 24)}
TEST_ONLY_TIME = "2026-07-13T00:00:00Z"
TEST_ONLY_HASH = "a" * 64


def _load_schemas() -> dict[str, dict[str, Any]]:
    actual = {path.name for path in SCHEMA_DIRECTORY.glob("*.schema.json")}
    assert actual == EXPECTED_SCHEMAS, (
        f"foundation schema inventory mismatch; missing={sorted(EXPECTED_SCHEMAS - actual)}, "
        f"unexpected={sorted(actual - EXPECTED_SCHEMAS)}"
    )
    return {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(SCHEMA_DIRECTORY.glob("*.schema.json"))
    }


def _registry(schemas: dict[str, dict[str, Any]]) -> Registry:
    resources = [(schema["$id"], Resource.from_contents(schema)) for schema in schemas.values()]
    return Registry().with_resources(resources)


def _validator(
    filename: str,
    schemas: dict[str, dict[str, Any]],
) -> Draft202012Validator:
    return Draft202012Validator(
        schemas[filename],
        registry=_registry(schemas),
        format_checker=FormatChecker(),
    )


def _identity_fixture() -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "context_id": TEST_ONLY_UUIDS[1],
        "territory_id": TEST_ONLY_UUIDS[2],
        "tenant_id": TEST_ONLY_UUIDS[3],
        "principal_kind": "agent",
        "principal_id": TEST_ONLY_UUIDS[4],
        "user_id": TEST_ONLY_UUIDS[5],
        "agent_definition_id": TEST_ONLY_UUIDS[6],
        "agent_instance_id": TEST_ONLY_UUIDS[7],
        "domain_id": TEST_ONLY_UUIDS[8],
        "team_id": TEST_ONLY_UUIDS[9],
        "session_id": TEST_ONLY_UUIDS[10],
        "task_id": TEST_ONLY_UUIDS[11],
        "plaza_id": TEST_ONLY_UUIDS[12],
        "credential_version": 1,
        "policy_version": "1.0.0",
        "purpose": "contract-validation",
        "scope_ceiling": "agent_private",
        "capabilities": ["memory:capture", "memory:search"],
        "issued_at": TEST_ONLY_TIME,
        "expires_at": "2026-07-13T00:05:00Z",
    }


def _fixtures() -> dict[str, dict[str, Any]]:
    return {
        "identity-context.schema.json": _identity_fixture(),
        "session.schema.json": {
            "schema_version": "1.0.0",
            "session_id": TEST_ONLY_UUIDS[10],
            "territory_id": TEST_ONLY_UUIDS[2],
            "tenant_id": TEST_ONLY_UUIDS[3],
            "user_id": TEST_ONLY_UUIDS[5],
            "agent_definition_id": TEST_ONLY_UUIDS[6],
            "agent_instance_id": TEST_ONLY_UUIDS[7],
            "task_id": TEST_ONLY_UUIDS[11],
            "state": "active",
            "session_seq_high_watermark": 0,
            "started_at": TEST_ONLY_TIME,
            "ended_at": None,
            "created_at": TEST_ONLY_TIME,
            "updated_at": TEST_ONLY_TIME,
            "identity_context_hash": TEST_ONLY_HASH,
        },
        "memory-event.schema.json": {
            "schema_version": "1.0.0",
            "event_id": TEST_ONLY_UUIDS[13],
            "idempotency_key": TEST_ONLY_UUIDS[14],
            "territory_id": TEST_ONLY_UUIDS[2],
            "tenant_id": TEST_ONLY_UUIDS[3],
            "user_id": TEST_ONLY_UUIDS[5],
            "agent_instance_id": TEST_ONLY_UUIDS[7],
            "session_id": TEST_ONLY_UUIDS[10],
            "task_id": TEST_ONLY_UUIDS[11],
            "session_seq": 1,
            "event_type": "user_prompt_captured",
            "classification": "private",
            "occurred_at": TEST_ONLY_TIME,
            "ingested_at": TEST_ONLY_TIME,
            "payload_ref": "object://test-only/event/13",
            "payload_hash": TEST_ONLY_HASH,
        },
        "memory-record.schema.json": {
            "schema_version": "1.0.0",
            "memory_id": TEST_ONLY_UUIDS[15],
            "version_id": TEST_ONLY_UUIDS[16],
            "territory_id": TEST_ONLY_UUIDS[2],
            "tenant_id": TEST_ONLY_UUIDS[3],
            "user_id": TEST_ONLY_UUIDS[5],
            "agent_definition_id": TEST_ONLY_UUIDS[6],
            "agent_instance_id": TEST_ONLY_UUIDS[7],
            "source_session_id": TEST_ONLY_UUIDS[10],
            "source_task_id": TEST_ONLY_UUIDS[11],
            "source_event_id": TEST_ONLY_UUIDS[13],
            "scope": "session_private",
            "classification": "private",
            "record_state": "active",
            "index_state": "pending",
            "content_ref": "object://test-only/memory/15/16",
            "content_hash": TEST_ONLY_HASH,
            "parent_version_id": None,
            "derived_from_version_ids": [],
            "occurred_at": TEST_ONLY_TIME,
            "ingested_at": TEST_ONLY_TIME,
            "created_at": TEST_ONLY_TIME,
            "updated_at": TEST_ONLY_TIME,
            "valid_from": TEST_ONLY_TIME,
            "valid_to": None,
            "superseded_at": None,
            "tombstoned_at": None,
            "retention_class": "session-standard",
            "policy_version": "1.0.0",
        },
        "memory-grant.schema.json": {
            "schema_version": "1.0.0",
            "grant_id": TEST_ONLY_UUIDS[17],
            "territory_id": TEST_ONLY_UUIDS[2],
            "tenant_id": TEST_ONLY_UUIDS[3],
            "subject_kind": "agent_instance",
            "subject_id": TEST_ONLY_UUIDS[7],
            "resource_kind": "memory",
            "resource_id": TEST_ONLY_UUIDS[15],
            "scope_ceiling": "session_private",
            "capabilities": ["memory:read"],
            "purpose": "contract-validation",
            "status": "active",
            "issued_by_principal_id": TEST_ONLY_UUIDS[18],
            "policy_version": "1.0.0",
            "valid_from": TEST_ONLY_TIME,
            "valid_to": "2026-07-13T00:05:00Z",
            "revoked_at": None,
        },
        "promotion-case.schema.json": {
            "schema_version": "1.0.0",
            "promotion_case_id": TEST_ONLY_UUIDS[19],
            "territory_id": TEST_ONLY_UUIDS[2],
            "tenant_id": TEST_ONLY_UUIDS[3],
            "source_memory_id": TEST_ONLY_UUIDS[15],
            "source_version_id": TEST_ONLY_UUIDS[16],
            "requested_target_scope": "team_private",
            "status": "proposed",
            "requested_by_principal_id": TEST_ONLY_UUIDS[4],
            "evidence_hashes": [TEST_ONLY_HASH],
            "required_gates": ["provenance", "classification", "triumvirate"],
            "approvals": [],
            "decision": None,
            "materialized_version_id": None,
            "audit_record_hash": None,
            "created_at": TEST_ONLY_TIME,
            "updated_at": TEST_ONLY_TIME,
            "decided_at": None,
            "materialized_at": None,
            "revoked_at": None,
            "policy_version": "1.0.0",
        },
    }


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def test_all_foundation_schemas_are_valid_draft_2020_12() -> None:
    schemas = _load_schemas()
    for schema in schemas.values():
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        Draft202012Validator.check_schema(schema)


def test_sanitized_test_only_fixtures_satisfy_every_record_contract() -> None:
    schemas = _load_schemas()
    for filename, fixture in _fixtures().items():
        _validator(filename, schemas).validate(fixture)


def test_contracts_reject_non_v7_identity_and_unknown_properties() -> None:
    schemas = _load_schemas()
    validator = _validator("identity-context.schema.json", schemas)

    non_v7 = deepcopy(_identity_fixture())
    non_v7["session_id"] = "550e8400-e29b-41d4-a716-446655440000"
    assert list(validator.iter_errors(non_v7))

    widened = deepcopy(_identity_fixture())
    widened["requested_tenant_override"] = TEST_ONLY_UUIDS[23]
    assert list(validator.iter_errors(widened))


def test_contracts_define_no_implicit_shared_default_or_current_authority() -> None:
    schemas = _load_schemas()
    prohibited = {"shared", "default", "current"}
    for filename, schema in schemas.items():
        for node in _walk(schema):
            assert node.get("default") not in prohibited, filename
