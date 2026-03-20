"""Create form_submission table for lead capture and other forms.

Revision ID: 102
Revises: 101
Create Date: 2025-03-19 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '102'
down_revision: Union[str, None] = '101'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create form_submission table for storing form data.

    Supports enterprise lead capture forms and future form types.
    Uses JSONB for flexible answer storage.
    """
    op.create_table(
        'form_submission',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('form_type', sa.String(50), nullable=False),
        sa.Column('answers', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            'status',
            sa.String(20),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(),
            nullable=False,
            server_default=sa.text('CURRENT_TIMESTAMP'),
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(),
            nullable=False,
            server_default=sa.text('CURRENT_TIMESTAMP'),
        ),
        sa.PrimaryKeyConstraint('id'),
        # SET NULL on delete: When a user is deleted, we preserve form submissions
        # for business data retention (lead capture records). This is intentional -
        # we want to keep the submission history even if the user account is removed.
        sa.ForeignKeyConstraint(
            ['user_id'],
            ['user.id'],
            name='form_submission_user_fkey',
            ondelete='SET NULL',
        ),
    )
    op.create_index(
        op.f('ix_form_submission_form_type'),
        'form_submission',
        ['form_type'],
        unique=False,
    )
    op.create_index(
        'ix_form_submission_form_type_created_at',
        'form_submission',
        ['form_type', 'created_at'],
        unique=False,
    )


def downgrade() -> None:
    """Remove form_submission table."""
    op.drop_index(
        'ix_form_submission_form_type_created_at', table_name='form_submission'
    )
    op.drop_index(op.f('ix_form_submission_form_type'), table_name='form_submission')
    op.drop_table('form_submission')
