"""Add agent_settings columns to enterprise settings tables.

Revision ID: 102
Revises: 101
Create Date: 2026-03-22 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '102'
down_revision: Union[str, None] = '101'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_EMPTY_JSON = sa.text("'{}'::json")


def upgrade() -> None:
    op.add_column(
        'user_settings',
        sa.Column('agent_settings', sa.JSON(), nullable=False, server_default=_EMPTY_JSON),
    )
    op.add_column(
        'org_member',
        sa.Column('agent_settings', sa.JSON(), nullable=False, server_default=_EMPTY_JSON),
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


def downgrade() -> None:
    op.drop_column('org_member', 'agent_settings')
    op.drop_column('user_settings', 'agent_settings')
