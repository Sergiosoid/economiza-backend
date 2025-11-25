"""add consent and deleted_at to users

Revision ID: 002_consent_deleted
Revises: 001_initial
Create Date: 2024-01-01 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '002_consent_deleted'
down_revision: Union[str, None] = '001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Adicionar campo consent_given
    op.add_column('users', sa.Column('consent_given', sa.Boolean(), nullable=False, server_default='false'))
    
    # Adicionar campo deleted_at
    op.add_column('users', sa.Column('deleted_at', postgresql.TIMESTAMP(timezone=True), nullable=True))
    
    # Criar índice para deleted_at
    op.create_index('ix_users_deleted_at', 'users', ['deleted_at'])


def downgrade() -> None:
    # Remover índice
    op.drop_index('ix_users_deleted_at', table_name='users')
    
    # Remover colunas
    op.drop_column('users', 'deleted_at')
    op.drop_column('users', 'consent_given')

