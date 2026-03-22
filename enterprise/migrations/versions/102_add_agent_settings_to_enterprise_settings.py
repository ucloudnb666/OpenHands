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


def downgrade() -> None:
    op.drop_column('org_member', 'agent_settings')
    op.drop_column('user_settings', 'agent_settings')
