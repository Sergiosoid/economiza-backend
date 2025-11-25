"""add stripe subscription fields to users

Revision ID: 003_stripe_subscription
Revises: 002_consent_deleted
Create Date: 2024-01-01 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '003_stripe_subscription'
down_revision: Union[str, None] = '002_consent_deleted'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Adicionar campo is_pro
    op.add_column('users', sa.Column('is_pro', sa.Boolean(), nullable=False, server_default='false'))
    
    # Adicionar campo subscription_id
    op.add_column('users', sa.Column('subscription_id', sa.String(255), nullable=True))
    
    # Criar índices
    op.create_index('ix_users_is_pro', 'users', ['is_pro'])
    op.create_index('ix_users_subscription_id', 'users', ['subscription_id'])


def downgrade() -> None:
    # Remover índices
    op.drop_index('ix_users_subscription_id', table_name='users')
    op.drop_index('ix_users_is_pro', table_name='users')
    
    # Remover colunas
    op.drop_column('users', 'subscription_id')
    op.drop_column('users', 'is_pro')

