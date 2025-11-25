"""add consent_terms to users

Revision ID: 004_consent_terms
Revises: 003_add_stripe_subscription
Create Date: 2024-01-01 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '004_consent_terms'
down_revision: Union[str, None] = '003_add_stripe_subscription'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Adicionar campo consent_terms
    op.add_column('users', sa.Column('consent_terms', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    op.drop_column('users', 'consent_terms')

