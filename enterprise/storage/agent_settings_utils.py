from __future__ import annotations

from typing import Any, Mapping

from storage.org import Org
from storage.org_member import OrgMember

_SCHEMA_VERSION = 1


def ensure_schema_version(agent_settings: Mapping[str, Any] | None) -> dict[str, Any]:
    normalized = dict(agent_settings or {})
    if normalized and 'schema_version' not in normalized:
        normalized['schema_version'] = _SCHEMA_VERSION
    return normalized


def merge_agent_settings(
    base: Mapping[str, Any] | None,
    updates: Mapping[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(base or {})
    for key, value in (updates or {}).items():
        if key == 'schema_version':
            continue
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return ensure_schema_version(merged)


def get_org_agent_settings(org: Org) -> dict[str, Any]:
    return ensure_schema_version(dict(getattr(org, 'agent_settings', {}) or {}))


def get_org_member_agent_settings(org_member: OrgMember) -> dict[str, Any]:
    return ensure_schema_version(dict(getattr(org_member, 'agent_settings', {}) or {}))
