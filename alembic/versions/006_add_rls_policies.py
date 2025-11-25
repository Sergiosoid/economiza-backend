"""add RLS policies

Revision ID: 006_add_rls_policies
Revises: 005_add_stripe_customer_id
Create Date: 2024-01-20 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = '006_add_rls_policies'
down_revision = '005_add_stripe_customer_id'
branch_labels = None
depends_on = None


def upgrade():
    """
    Adiciona Row Level Security (RLS) policies para proteger dados por usuário.
    
    IMPORTANTE: Esta migration deve ser revisada antes de aplicar em produção.
    As policies assumem que o Supabase Auth está configurado e que auth.uid() retorna o UUID do usuário.
    
    Em desenvolvimento, as policies podem ser desabilitadas se necessário.
    """
    # Habilitar RLS nas tabelas principais
    op.execute(text("""
        ALTER TABLE receipts ENABLE ROW LEVEL SECURITY;
        ALTER TABLE receipt_items ENABLE ROW LEVEL SECURITY;
        ALTER TABLE products ENABLE ROW LEVEL SECURITY;
        ALTER TABLE analytics_cache ENABLE ROW LEVEL SECURITY;
    """))
    
    # Policy para receipts: usuários só veem seus próprios receipts
    op.execute(text("""
        CREATE POLICY "users_select_own_receipts" ON receipts
        FOR SELECT
        USING (user_id::text = auth.uid()::text);
    """))
    
    op.execute(text("""
        CREATE POLICY "users_insert_own_receipts" ON receipts
        FOR INSERT
        WITH CHECK (user_id::text = auth.uid()::text);
    """))
    
    op.execute(text("""
        CREATE POLICY "users_update_own_receipts" ON receipts
        FOR UPDATE
        USING (user_id::text = auth.uid()::text)
        WITH CHECK (user_id::text = auth.uid()::text);
    """))
    
    op.execute(text("""
        CREATE POLICY "users_delete_own_receipts" ON receipts
        FOR DELETE
        USING (user_id::text = auth.uid()::text);
    """))
    
    # Policy para receipt_items: baseado no receipt.user_id
    op.execute(text("""
        CREATE POLICY "users_select_own_receipt_items" ON receipt_items
        FOR SELECT
        USING (
            EXISTS (
                SELECT 1 FROM receipts
                WHERE receipts.id = receipt_items.receipt_id
                AND receipts.user_id::text = auth.uid()::text
            )
        );
    """))
    
    op.execute(text("""
        CREATE POLICY "users_insert_own_receipt_items" ON receipt_items
        FOR INSERT
        WITH CHECK (
            EXISTS (
                SELECT 1 FROM receipts
                WHERE receipts.id = receipt_items.receipt_id
                AND receipts.user_id::text = auth.uid()::text
            )
        );
    """))
    
    # Policy para products: permitir leitura para todos, escrita apenas para admins (futuro)
    # Por enquanto, permitir leitura pública de produtos
    op.execute(text("""
        CREATE POLICY "users_select_products" ON products
        FOR SELECT
        USING (true);
    """))
    
    # Policy para analytics_cache: usuários só veem seus próprios caches
    op.execute(text("""
        CREATE POLICY "users_select_own_analytics_cache" ON analytics_cache
        FOR SELECT
        USING (user_id::text = auth.uid()::text);
    """))
    
    op.execute(text("""
        CREATE POLICY "users_insert_own_analytics_cache" ON analytics_cache
        FOR INSERT
        WITH CHECK (user_id::text = auth.uid()::text);
    """))
    
    op.execute(text("""
        CREATE POLICY "users_update_own_analytics_cache" ON analytics_cache
        FOR UPDATE
        USING (user_id::text = auth.uid()::text)
        WITH CHECK (user_id::text = auth.uid()::text);
    """))


def downgrade():
    """Remove todas as RLS policies e desabilita RLS."""
    op.execute(text("""
        DROP POLICY IF EXISTS "users_select_own_receipts" ON receipts;
        DROP POLICY IF EXISTS "users_insert_own_receipts" ON receipts;
        DROP POLICY IF EXISTS "users_update_own_receipts" ON receipts;
        DROP POLICY IF EXISTS "users_delete_own_receipts" ON receipts;
        
        DROP POLICY IF EXISTS "users_select_own_receipt_items" ON receipt_items;
        DROP POLICY IF EXISTS "users_insert_own_receipt_items" ON receipt_items;
        
        DROP POLICY IF EXISTS "users_select_products" ON products;
        
        DROP POLICY IF EXISTS "users_select_own_analytics_cache" ON analytics_cache;
        DROP POLICY IF EXISTS "users_insert_own_analytics_cache" ON analytics_cache;
        DROP POLICY IF EXISTS "users_update_own_analytics_cache" ON analytics_cache;
    """))
    
    op.execute(text("""
        ALTER TABLE receipts DISABLE ROW LEVEL SECURITY;
        ALTER TABLE receipt_items DISABLE ROW LEVEL SECURITY;
        ALTER TABLE products DISABLE ROW LEVEL SECURITY;
        ALTER TABLE analytics_cache DISABLE ROW LEVEL SECURITY;
    """))

