from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from storage.org import Org
from storage.org_member import OrgMember

from openhands.utils.jsonpatch_compat import make_patch


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


def merge_agent_settings(
    base: Mapping[str, Any] | None,
    updates: Mapping[str, Any] | None,
) -> dict[str, Any]:
    base_settings = dict(base or {})
    target_settings = _apply_updates(base_settings, updates)
    return make_patch(base_settings, target_settings).apply(base_settings)


def get_org_agent_settings(org: Org) -> dict[str, Any]:
    return dict(getattr(org, "agent_settings", {}) or {})


def get_org_member_agent_settings(org_member: OrgMember) -> dict[str, Any]:
    return dict(getattr(org_member, "agent_settings", {}) or {})


def get_org_conversation_settings(org: Org) -> dict[str, Any]:
    return dict(getattr(org, "conversation_settings", {}) or {})


def get_org_member_conversation_settings(org_member: OrgMember) -> dict[str, Any]:
    return dict(getattr(org_member, "conversation_settings", {}) or {})


def compute_agent_settings_overrides(
    base: Mapping[str, Any] | None,
    effective: Mapping[str, Any] | None,
) -> dict[str, Any]:
    base_settings = dict(base or {})
    effective_settings = dict(effective or {})

    overrides: dict[str, Any] = {}
    for operation in make_patch(base_settings, effective_settings).patch:
        key = _path_to_key(operation["path"])
        if key == "schema_version":
            continue
        overrides[key] = None if operation["op"] == "remove" else operation["value"]
    return overrides
