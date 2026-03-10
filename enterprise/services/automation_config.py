"""Automation config extraction and validation.

NOTE: This is a stub for Task 2 (CRUD API) development.
Task 1 (Data Foundation) will provide the full implementation.
"""

import ast

from pydantic import BaseModel, Field


class CronTriggerModel(BaseModel):
    schedule: str = Field(pattern=r'^(\S+\s+){4}\S+$')
    timezone: str = 'UTC'


class TriggersModel(BaseModel):
    cron: CronTriggerModel | None = None

    def model_post_init(self, __context: object) -> None:
        defined = [k for k in ('cron',) if getattr(self, k) is not None]
        if len(defined) != 1:
            raise ValueError(f'Exactly one trigger required, got: {defined or "none"}')


class AutomationConfigModel(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    triggers: TriggersModel
    description: str = ''


def extract_config(source: str) -> dict:
    """Extract __config__ dict from a Python automation file using AST."""
    tree = ast.parse(source)
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == '__config__':
                    return ast.literal_eval(node.value)
        if isinstance(node, ast.AnnAssign):
            if (
                isinstance(node.target, ast.Name)
                and node.target.id == '__config__'
                and node.value is not None
            ):
                return ast.literal_eval(node.value)
    raise ValueError('No __config__ dict found in automation file')


def validate_config(config: dict) -> AutomationConfigModel:
    """Validate a __config__ dict. Returns parsed model or raises ValidationError."""
    return AutomationConfigModel.model_validate(config)
