"""create initial database schema

Revision ID: 001_initial
Revises: 
Create Date: 2024-11-24 21:14:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('email', sa.String(255), nullable=False, unique=True),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_users_id', 'users', ['id'])
    op.create_index('ix_users_email', 'users', ['email'])

    # Create categories table
    op.create_table(
        'categories',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False, unique=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_categories_id', 'categories', ['id'])
    op.create_index('ix_categories_name', 'categories', ['name'])

    # Create products table
    op.create_table(
        'products',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('normalized_name', sa.String(255), nullable=False),
        sa.Column('barcode', sa.String(50), nullable=True),
        sa.Column('category_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id']),
    )
    op.create_index('ix_products_id', 'products', ['id'])
    op.create_index('ix_products_normalized_name', 'products', ['normalized_name'])
    op.create_index('ix_products_barcode', 'products', ['barcode'])

    # Create receipts table
    op.create_table(
        'receipts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('access_key', sa.String(255), nullable=False),
        sa.Column('raw_qr_text', sa.String(500), nullable=True),
        sa.Column('total_value', sa.Numeric(10, 2), nullable=False),
        sa.Column('subtotal', sa.Numeric(10, 2), nullable=False),
        sa.Column('total_tax', sa.Numeric(10, 2), nullable=False),
        sa.Column('emitted_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('store_name', sa.String(255), nullable=True),
        sa.Column('store_cnpj', sa.String(18), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
    )
    op.create_index('ix_receipts_id', 'receipts', ['id'])
    op.create_index('ix_receipts_user_id', 'receipts', ['user_id'])
    op.create_index('ix_receipts_access_key', 'receipts', ['access_key'])

    # Create receipt_items table
    op.create_table(
        'receipt_items',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('receipt_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('product_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('description', sa.String(255), nullable=False),
        sa.Column('quantity', sa.Numeric(10, 3), nullable=False),
        sa.Column('unit_price', sa.Numeric(10, 2), nullable=False),
        sa.Column('total_price', sa.Numeric(10, 2), nullable=False),
        sa.Column('tax_value', sa.Numeric(10, 2), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['receipt_id'], ['receipts.id']),
        sa.ForeignKeyConstraint(['product_id'], ['products.id']),
    )
    op.create_index('ix_receipt_items_id', 'receipt_items', ['id'])
    op.create_index('ix_receipt_items_receipt_id', 'receipt_items', ['receipt_id'])
    op.create_index('ix_receipt_items_product_id', 'receipt_items', ['product_id'])

    # Create analytics_cache table
    op.create_table(
        'analytics_cache',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('month', sa.String(7), nullable=False),
        sa.Column('data', postgresql.JSON, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
    )
    op.create_index('ix_analytics_cache_id', 'analytics_cache', ['id'])
    op.create_index('ix_analytics_cache_user_id', 'analytics_cache', ['user_id'])
    op.create_index('ix_analytics_cache_month', 'analytics_cache', ['month'])


def downgrade() -> None:
    op.drop_index('ix_analytics_cache_month', table_name='analytics_cache')
    op.drop_index('ix_analytics_cache_user_id', table_name='analytics_cache')
    op.drop_index('ix_analytics_cache_id', table_name='analytics_cache')
    op.drop_table('analytics_cache')
    
    op.drop_index('ix_receipt_items_product_id', table_name='receipt_items')
    op.drop_index('ix_receipt_items_receipt_id', table_name='receipt_items')
    op.drop_index('ix_receipt_items_id', table_name='receipt_items')
    op.drop_table('receipt_items')
    
    op.drop_index('ix_receipts_access_key', table_name='receipts')
    op.drop_index('ix_receipts_user_id', table_name='receipts')
    op.drop_index('ix_receipts_id', table_name='receipts')
    op.drop_table('receipts')
    
    op.drop_index('ix_products_barcode', table_name='products')
    op.drop_index('ix_products_normalized_name', table_name='products')
    op.drop_index('ix_products_id', table_name='products')
    op.drop_table('products')
    
    op.drop_index('ix_categories_name', table_name='categories')
    op.drop_index('ix_categories_id', table_name='categories')
    op.drop_table('categories')
    
    op.drop_index('ix_users_email', table_name='users')
    op.drop_index('ix_users_id', table_name='users')
    op.drop_table('users')

