"""add shopping list executions

Revision ID: 009_add_shopping_list_executions
Revises: 008_add_units_and_shopping_lists
Create Date: 2024-01-27 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import UUID, JSONB
import uuid

# revision identifiers, used by Alembic.
revision = '009_add_shopping_list_executions'
down_revision = '008_add_units_and_shopping_lists'
branch_labels = None
depends_on = None


def upgrade():
    """
    Adiciona tabela de execuções de sincronização (histórico)
    para comparar listas de compras com notas fiscais.
    """
    op.create_table(
        'shopping_list_executions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('shopping_list_id', UUID(as_uuid=True), nullable=False),
        sa.Column('receipt_id', UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False),
        sa.Column('planned_total', sa.Numeric(12, 2), nullable=True),
        sa.Column('real_total', sa.Numeric(12, 2), nullable=True),
        sa.Column('difference', sa.Numeric(12, 2), nullable=True),
        sa.Column('difference_percent', sa.Numeric(6, 2), nullable=True),
        sa.Column('summary', JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['shopping_list_id'], ['shopping_lists.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['receipt_id'], ['receipts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_shopping_list_executions_list_id', 'shopping_list_executions', ['shopping_list_id'])
    op.create_index('ix_shopping_list_executions_receipt_id', 'shopping_list_executions', ['receipt_id'])
    op.create_index('ix_shopping_list_executions_user_id', 'shopping_list_executions', ['user_id'])


def downgrade():
    """Remove tabela de execuções de sincronização"""
    op.drop_index('ix_shopping_list_executions_user_id', table_name='shopping_list_executions')
    op.drop_index('ix_shopping_list_executions_receipt_id', table_name='shopping_list_executions')
    op.drop_index('ix_shopping_list_executions_list_id', table_name='shopping_list_executions')
    op.drop_table('shopping_list_executions')

