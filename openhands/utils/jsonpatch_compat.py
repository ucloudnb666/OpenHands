from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

JsonPatchOperation = dict[str, Any]


def _escape_token(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _unescape_token(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def _join_path(base: str, token: str) -> str:
    return f"{base}/{_escape_token(token)}" if base else f"/{_escape_token(token)}"


def _split_path(path: str) -> list[str]:
    if not path:
        return []
    if not path.startswith("/"):
        raise ValueError(f"Invalid JSON patch path: {path}")
    return [_unescape_token(token) for token in path[1:].split("/")]


def _resolve_parent(document: Any, path: str) -> tuple[Any, str | None]:
    tokens = _split_path(path)
    if not tokens:
        return None, None

    current = document
    for token in tokens[:-1]:
        if isinstance(current, dict):
            current = current[token]
            continue
        if isinstance(current, list):
            current = current[int(token)]
            continue
        raise TypeError(f"Unsupported JSON patch container at {path}")

    return current, tokens[-1]


@dataclass(frozen=True)
class JsonPatch:
    operations: list[JsonPatchOperation]

    @property
    def patch(self) -> list[JsonPatchOperation]:
        return deepcopy(self.operations)

    def apply(self, document: Any) -> Any:
        result = deepcopy(document)
        for operation in self.operations:
            op = operation["op"]
            path = operation["path"]
            value = deepcopy(operation.get("value"))

            if op == "replace" and not path:
                result = value
                continue
            if op == "add" and not path:
                result = value
                continue
            if op == "remove" and not path:
                result = None
                continue

            parent, token = _resolve_parent(result, path)
            if token is None:
                raise ValueError(f"Invalid JSON patch path: {path}")

            if isinstance(parent, dict):
                if op in {"add", "replace"}:
                    parent[token] = value
                elif op == "remove":
                    parent.pop(token, None)
                else:
                    raise ValueError(f"Unsupported JSON patch operation: {op}")
                continue

            if isinstance(parent, list):
                index = len(parent) if token == "-" else int(token)
                if op == "add":
                    parent.insert(index, value)
                elif op == "replace":
                    parent[index] = value
                elif op == "remove":
                    parent.pop(index)
                else:
                    raise ValueError(f"Unsupported JSON patch operation: {op}")
                continue

            raise TypeError(f"Unsupported JSON patch container at {path}")

        return result


def _make_patch_operations(
    source: Any, target: Any, path: str = ""
) -> list[JsonPatchOperation]:
    if source == target:
        return []

    if isinstance(source, dict) and isinstance(target, dict):
        operations: list[JsonPatchOperation] = []

        for key in sorted(set(source) - set(target)):
            operations.append({"op": "remove", "path": _join_path(path, key)})

        for key in sorted(set(source) & set(target)):
            operations.extend(
                _make_patch_operations(source[key], target[key], _join_path(path, key))
            )

        for key in sorted(set(target) - set(source)):
            operations.append(
                {
                    "op": "add",
                    "path": _join_path(path, key),
                    "value": deepcopy(target[key]),
                }
            )

        return operations

    if isinstance(source, list) and isinstance(target, list):
        return [{"op": "replace", "path": path, "value": deepcopy(target)}]

    return [{"op": "replace", "path": path, "value": deepcopy(target)}]


def make_patch(source: Any, target: Any) -> JsonPatch:
    return JsonPatch(_make_patch_operations(source, target))


def deep_merge(
    base: dict[str, Any],
    updates: dict[str, Any],
) -> dict[str, Any]:
    """Recursively merge *updates* into a shallow copy of *base*.

    * Nested dicts are merged recursively.
    * ``None`` values in *updates* remove the corresponding key.
    * All other values overwrite.
    """
    result: dict[str, Any] = dict(base)
    for key, value in updates.items():
        if value is None:
            result.pop(key, None)
        elif isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result
