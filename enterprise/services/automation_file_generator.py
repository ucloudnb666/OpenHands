"""Automation file generator for simple mode (Phase 1).

NOTE: This is a stub for Task 2 (CRUD API) development.
Task 1 (Data Foundation) will provide the full implementation.
"""

import json

PROMPT_TEMPLATE = '''\
"""{name} — auto-generated from form input."""

__config__ = {config_json}

import os

from openhands.sdk import LLM, Conversation
from openhands.tools.preset.default import get_default_agent

llm = LLM(
    model=os.getenv("LLM_MODEL", "anthropic/claude-sonnet-4-5-20250929"),
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL"),
)
agent = get_default_agent(llm=llm, cli_mode=True)
conversation = Conversation(agent=agent, workspace=os.getcwd())

conversation.send_message({prompt!r})
conversation.run()
'''


def generate_automation_file(
    name: str,
    schedule: str,
    timezone: str,
    prompt: str,
    repository: str | None = None,
    branch: str | None = None,
) -> str:
    """Generate a Python automation file from form input."""
    config: dict = {
        'name': name,
        'triggers': {'cron': {'schedule': schedule, 'timezone': timezone}},
    }
    return PROMPT_TEMPLATE.format(
        name=name,
        config_json=json.dumps(config, indent=4),
        prompt=prompt,
    )
