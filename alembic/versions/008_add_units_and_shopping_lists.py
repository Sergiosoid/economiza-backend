"""add units and shopping lists

Revision ID: 008_add_units_and_shopping_lists
Revises: 007_add_credits_and_usage
Create Date: 2024-01-26 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import UUID, JSON
import uuid

# revision identifiers, used by Alembic.
revision = '008_add_units_and_shopping_lists'
down_revision = '007_add_credits_and_usage'
branch_labels = None
depends_on = None


def upgrade():
    """
    Adiciona tabelas de unidades e listas de compras.
    Pre-popula tabela units com unidades básicas.
    """
    # Criar tabela units
    op.create_table(
        'units',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('code', sa.String(10), nullable=False, unique=True),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('type', sa.String(16), nullable=False),
        sa.Column('multiplier', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_units_code', 'units', ['code'])
    op.create_index('ix_units_id', 'units', ['id'])

    # Criar tabela shopping_lists
    op.create_table(
        'shopping_lists',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(200), nullable=False, server_default='Minha lista'),
        sa.Column('is_shared', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('meta', JSON, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_shopping_lists_user_id', 'shopping_lists', ['user_id'])
    op.create_index('ix_shopping_lists_id', 'shopping_lists', ['id'])

    # Criar tabela shopping_list_items
    op.create_table(
        'shopping_list_items',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('shopping_list_id', UUID(as_uuid=True), nullable=False),
        sa.Column('product_id', UUID(as_uuid=True), nullable=True),
        sa.Column('description', sa.String(255), nullable=False),
        sa.Column('quantity', sa.Numeric(12, 3), nullable=False),
        sa.Column('unit_code', sa.String(10), nullable=False),
        sa.Column('unit_type', sa.String(16), nullable=False),
        sa.Column('unit_multiplier', sa.Integer(), nullable=False),
        sa.Column('price_estimate', sa.Numeric(12, 2), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['shopping_list_id'], ['shopping_lists.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='SET NULL'),
    )
    op.create_index('ix_shopping_list_items_shopping_list_id', 'shopping_list_items', ['shopping_list_id'])
    op.create_index('ix_shopping_list_items_product_id', 'shopping_list_items', ['product_id'])
    op.create_index('ix_shopping_list_items_id', 'shopping_list_items', ['id'])

    # Pre-popular tabela units com unidades básicas
    op.execute(text("""
        INSERT INTO units (id, code, name, type, multiplier) VALUES
        (gen_random_uuid(), 'un', 'Unidade', 'unit', 1),
        (gen_random_uuid(), 'kg', 'Quilo', 'weight', 1000),
        (gen_random_uuid(), 'g', 'Grama', 'weight', 1),
        (gen_random_uuid(), 'L', 'Litro', 'volume', 1000),
        (gen_random_uuid(), 'ml', 'Mililitro', 'volume', 1)
        ON CONFLICT (code) DO NOTHING;
    """))


def downgrade():
    """Remove tabelas de unidades e listas de compras"""
    op.drop_index('ix_shopping_list_items_id', table_name='shopping_list_items')
    op.drop_index('ix_shopping_list_items_product_id', table_name='shopping_list_items')
    op.drop_index('ix_shopping_list_items_shopping_list_id', table_name='shopping_list_items')
    op.drop_table('shopping_list_items')
    op.drop_index('ix_shopping_lists_id', table_name='shopping_lists')
    op.drop_index('ix_shopping_lists_user_id', table_name='shopping_lists')
    op.drop_table('shopping_lists')
    op.drop_index('ix_units_id', table_name='units')
    op.drop_index('ix_units_code', table_name='units')
    op.drop_table('units')

