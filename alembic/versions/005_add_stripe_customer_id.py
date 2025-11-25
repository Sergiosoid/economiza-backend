"""add stripe_customer_id to users

Revision ID: 005_stripe_customer_id
Revises: 004_consent_terms
Create Date: 2024-01-01 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '005_stripe_customer_id'
down_revision: Union[str, None] = '004_consent_terms'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Adicionar campo stripe_customer_id
    op.add_column('users', sa.Column('stripe_customer_id', sa.String(255), nullable=True))
    
    # Criar índice
    op.create_index('ix_users_stripe_customer_id', 'users', ['stripe_customer_id'])


def downgrade() -> None:
    # Remover índice
    op.drop_index('ix_users_stripe_customer_id', table_name='users')
    
    # Remover coluna
    op.drop_column('users', 'stripe_customer_id')

