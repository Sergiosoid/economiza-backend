"""add credits and usage tracking

Revision ID: 007_add_credits_and_usage
Revises: 006_add_rls_policies
Create Date: 2024-01-25 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = '007_add_credits_and_usage'
down_revision = '006_add_rls_policies'  # ou '005_stripe_customer_id' se 006 não existir
branch_labels = None
depends_on = None


def upgrade():
    """
    Adiciona campos de créditos e rastreamento de uso na tabela users.
    Também cria tabela credit_usage para histórico de consumo.
    """
    # Adicionar colunas de créditos na tabela users
    op.add_column('users', sa.Column('credits', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('users', sa.Column('credits_purchased', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('users', sa.Column('credits_used', sa.Integer(), nullable=False, server_default='0'))
    
    # Criar tabela credit_usage para histórico
    op.create_table(
        'credit_usage',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('credits_consumed', sa.Integer(), nullable=False),
        sa.Column('action_type', sa.String(50), nullable=False),  # 'scan', 'ai_analysis', etc.
        sa.Column('action_id', sa.UUID(), nullable=True),  # ID do receipt, etc.
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_credit_usage_user_id', 'credit_usage', ['user_id'])
    op.create_index('ix_credit_usage_created_at', 'credit_usage', ['created_at'])
    op.create_index('ix_credit_usage_action_type', 'credit_usage', ['action_type'])


def downgrade():
    """Remove campos de créditos e tabela de uso"""
    op.drop_index('ix_credit_usage_action_type', table_name='credit_usage')
    op.drop_index('ix_credit_usage_created_at', table_name='credit_usage')
    op.drop_index('ix_credit_usage_user_id', table_name='credit_usage')
    op.drop_table('credit_usage')
    op.drop_column('users', 'credits_used')
    op.drop_column('users', 'credits_purchased')
    op.drop_column('users', 'credits')

