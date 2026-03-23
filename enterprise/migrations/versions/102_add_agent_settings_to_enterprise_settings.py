"""Add agent_settings columns to enterprise settings tables.

Revision ID: 102
Revises: 101
Create Date: 2026-03-22 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "102"
down_revision: Union[str, None] = "101"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_EMPTY_JSON = sa.text("'{}'::json")


def upgrade() -> None:
    op.add_column(
        "user_settings",
        sa.Column(
            "agent_settings", sa.JSON(), nullable=False, server_default=_EMPTY_JSON
        ),
    )
    op.add_column(
        "org_member",
        sa.Column(
            "agent_settings", sa.JSON(), nullable=False, server_default=_EMPTY_JSON
        ),
    )

    op.execute(
        sa.text(
            """
            UPDATE user_settings
            SET agent_settings = jsonb_strip_nulls(
                jsonb_build_object(
                    'schema_version', 1,
                    'agent', agent,
                    'llm.model', llm_model,
                    'llm.base_url', llm_base_url,
                    'verification.confirmation_mode', confirmation_mode,
                    'verification.security_analyzer', security_analyzer,
                    'condenser.enabled', enable_default_condenser,
                    'condenser.max_size', condenser_max_size,
                    'max_iterations', max_iterations
                ) || COALESCE(agent_settings::jsonb, '{}'::jsonb)
            )::json
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE org_member
            SET agent_settings = jsonb_strip_nulls(
                jsonb_build_object(
                    'schema_version', 1,
                    'llm.model', llm_model,
                    'llm.base_url', llm_base_url,
                    'max_iterations', max_iterations
                ) || COALESCE(agent_settings::jsonb, '{}'::jsonb)
            )::json
            """
        )
    )

    op.alter_column("user_settings", "agent_settings", server_default=None)
    op.alter_column("org_member", "agent_settings", server_default=None)

    op.drop_column("user_settings", "agent")
    op.drop_column("user_settings", "max_iterations")
    op.drop_column("user_settings", "security_analyzer")
    op.drop_column("user_settings", "confirmation_mode")
    op.drop_column("user_settings", "llm_model")
    op.drop_column("user_settings", "llm_base_url")
    op.drop_column("user_settings", "enable_default_condenser")
    op.drop_column("user_settings", "condenser_max_size")


def downgrade() -> None:
    op.add_column("user_settings", sa.Column("agent", sa.String(), nullable=True))
    op.add_column(
        "user_settings", sa.Column("max_iterations", sa.Integer(), nullable=True)
    )
    op.add_column(
        "user_settings", sa.Column("security_analyzer", sa.String(), nullable=True)
    )
    op.add_column(
        "user_settings", sa.Column("confirmation_mode", sa.Boolean(), nullable=True)
    )
    op.add_column("user_settings", sa.Column("llm_model", sa.String(), nullable=True))
    op.add_column(
        "user_settings", sa.Column("llm_base_url", sa.String(), nullable=True)
    )
    op.add_column(
        "user_settings",
        sa.Column(
            "enable_default_condenser",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "user_settings", sa.Column("condenser_max_size", sa.Integer(), nullable=True)
    )

    op.execute(
        sa.text(
            """
            UPDATE user_settings
            SET
                agent = agent_settings ->> 'agent',
                max_iterations = NULLIF(agent_settings ->> 'max_iterations', '')::integer,
                security_analyzer =
                    agent_settings ->> 'verification.security_analyzer',
                confirmation_mode = CASE
                    WHEN agent_settings::jsonb ? 'verification.confirmation_mode'
                    THEN (agent_settings ->> 'verification.confirmation_mode')::boolean
                    ELSE NULL
                END,
                llm_model = agent_settings ->> 'llm.model',
                llm_base_url = agent_settings ->> 'llm.base_url',
                enable_default_condenser = CASE
                    WHEN agent_settings::jsonb ? 'condenser.enabled'
                    THEN (agent_settings ->> 'condenser.enabled')::boolean
                    ELSE TRUE
                END,
                condenser_max_size =
                    NULLIF(agent_settings ->> 'condenser.max_size', '')::integer
            """
        )
    )

    op.drop_column("org_member", "agent_settings")
    op.drop_column("user_settings", "agent_settings")
