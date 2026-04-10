from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from storage.org import Org
from storage.org_member import OrgMember

from openhands.utils.jsonpatch_compat import make_patch

_SCHEMA_VERSION = 1


def _path_to_key(path: str) -> str:
    return path.removeprefix("/").replace("/", ".")


def _apply_updates(
    base: Mapping[str, Any] | None,
    updates: Mapping[str, Any] | None,
) -> dict[str, Any]:
    target = deepcopy(dict(base or {}))
    for key, value in (updates or {}).items():
        if key == "schema_version":
            continue
        if value is None:
            target.pop(key, None)
        else:
            target[key] = value
    return target


def ensure_schema_version(agent_settings: Mapping[str, Any] | None) -> dict[str, Any]:
    normalized = dict(agent_settings or {})
    if normalized and "schema_version" not in normalized:
        normalized["schema_version"] = _SCHEMA_VERSION
    return normalized


def merge_agent_settings(
    base: Mapping[str, Any] | None,
    updates: Mapping[str, Any] | None,
) -> dict[str, Any]:
    base_settings = ensure_schema_version(base)
    target_settings = ensure_schema_version(_apply_updates(base_settings, updates))
    return ensure_schema_version(
        make_patch(base_settings, target_settings).apply(base_settings)
    )


def get_org_agent_settings(org: Org) -> dict[str, Any]:
    return ensure_schema_version(dict(getattr(org, "agent_settings", {}) or {}))


def get_org_member_agent_settings(org_member: OrgMember) -> dict[str, Any]:
    return ensure_schema_version(dict(getattr(org_member, "agent_settings", {}) or {}))


def compute_agent_settings_overrides(
    base: Mapping[str, Any] | None,
    effective: Mapping[str, Any] | None,
) -> dict[str, Any]:
    base_settings = ensure_schema_version(base)
    effective_settings = ensure_schema_version(effective)

    overrides: dict[str, Any] = {}
    for operation in make_patch(base_settings, effective_settings).patch:
        key = _path_to_key(operation["path"])
        if key == "schema_version":
            continue
        overrides[key] = None if operation["op"] == "remove" else operation["value"]
    return ensure_schema_version(overrides)
