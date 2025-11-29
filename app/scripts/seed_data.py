"""
Script para popular o banco de dados com dados realistas de compras de supermercado.
Gera 8 meses de histórico com notas fiscais variadas para habilitar todos os recursos do MVP.

Uso:
    python -m app.scripts.seed_data
"""
import sys
import os
import random
import hashlib
from datetime import datetime, timedelta
from uuid import UUID, uuid4
from typing import Dict, List, Optional

# Adicionar o diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.database import SessionLocal
from app.models.user import User
from app.models.receipt import Receipt
from app.models.receipt_item import ReceiptItem
from app.models.category import Category
from app.services.product_matcher import get_or_create_product_from_item
from app.utils.encryption import encrypt_sensitive_data

# Configurações
DEV_USER_EMAIL = "dev@example.com"
DEV_USER_ID = UUID("00000000-0000-0000-0000-000000000001")

# Mercados disponíveis
STORES = [
    {"name": "Carrefour", "cnpj": "12345678000199"},
    {"name": "Assaí", "cnpj": "23456789000100"},
    {"name": "Atacadão", "cnpj": "34567890000111"},
    {"name": "Maxxi", "cnpj": "45678901000122"},
    {"name": "Dia", "cnpj": "56789012000133"},
    {"name": "Coop", "cnpj": "67890123000144"},
    {"name": "Sonda", "cnpj": "78901234000155"},
    {"name": "Pão de Açúcar", "cnpj": "89012345000166"},
]

# Produtos disponíveis com preços base e categorias
PRODUCTS = [
    {"name": "Arroz", "base_price": (12.0, 25.0), "category": "Alimentos"},
    {"name": "Feijão", "base_price": (6.0, 12.0), "category": "Alimentos"},
    {"name": "Óleo", "base_price": (5.0, 8.0), "category": "Alimentos"},
    {"name": "Açúcar", "base_price": (4.0, 7.0), "category": "Alimentos"},
    {"name": "Café", "base_price": (8.0, 18.0), "category": "Alimentos"},
    {"name": "Carne bovina", "base_price": (35.0, 60.0), "category": "Açougue"},
    {"name": "Frango", "base_price": (12.0, 22.0), "category": "Açougue"},
    {"name": "Sabonete", "base_price": (3.0, 6.0), "category": "Higiene"},
    {"name": "Detergente", "base_price": (2.5, 5.0), "category": "Limpeza"},
    {"name": "Amaciante", "base_price": (8.0, 15.0), "category": "Limpeza"},
    {"name": "Shampoo", "base_price": (8.0, 25.0), "category": "Higiene"},
    {"name": "Cerveja", "base_price": (3.0, 8.0), "category": "Bebidas"},
    {"name": "Refrigerante", "base_price": (5.0, 12.0), "category": "Bebidas"},
    {"name": "Macarrão", "base_price": (3.0, 7.0), "category": "Alimentos"},
    {"name": "Tomate", "base_price": (4.0, 10.0), "category": "Hortifruti"},
    {"name": "Cebola", "base_price": (3.0, 8.0), "category": "Hortifruti"},
    {"name": "Batata", "base_price": (4.0, 9.0), "category": "Hortifruti"},
    {"name": "Pão francês", "base_price": (0.5, 1.5), "category": "Padaria"},
    {"name": "Biscoito", "base_price": (3.0, 8.0), "category": "Alimentos"},
    {"name": "Leite", "base_price": (4.0, 7.0), "category": "Frios"},
    {"name": "Queijo", "base_price": (15.0, 35.0), "category": "Frios"},
    {"name": "Presunto", "base_price": (12.0, 25.0), "category": "Frios"},
]


def get_or_create_category(db, category_name: str) -> Optional[UUID]:
    """Busca ou cria uma categoria."""
    category = db.query(Category).filter(Category.name == category_name).first()
    if category:
        return category.id
    
    # Criar nova categoria
    category = Category(name=category_name)
    db.add(category)
    db.flush()
    return category.id


def get_or_create_user(db) -> User:
    """Busca ou cria o usuário de desenvolvimento."""
    user = db.query(User).filter(User.email == DEV_USER_EMAIL).first()
    
    if user:
        print(f"[OK] Usuário encontrado: {user.email} (ID: {user.id})")
        return user
    
    # Criar novo usuário
    user = User(
        id=DEV_USER_ID,
        email=DEV_USER_EMAIL,
        password_hash="dev_seed",
        consent_given=True,
        consent_terms=True,
        is_pro=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    print(f"[OK] Usuário criado: {user.email} (ID: {user.id})")
    return user


def generate_access_key(store_name: str, emitted_at: datetime, index: int) -> str:
    """Gera uma access_key única e determinística para idempotência."""
    # Usar hash para garantir idempotência
    key_string = f"{DEV_USER_EMAIL}_{store_name}_{emitted_at.isoformat()}_{index}"
    hash_value = hashlib.sha256(key_string.encode()).hexdigest()
    # Pegar primeiros 44 caracteres (formato de chave de acesso)
    return hash_value[:44]


def generate_receipt_date(year: int, month: int, week: int, day_in_week: int) -> datetime:
    """Gera uma data de emissão para a nota."""
    # Primeiro dia do mês
    base_date = datetime(year, month, 1)
    
    # Calcular qual semana do mês (0-3)
    week_offset = week * 7
    
    # Dia da semana (0=segunda, 6=domingo)
    day_offset = day_in_week
    
    # Data final
    receipt_date = base_date + timedelta(days=week_offset + day_offset)
    
    # Ajustar hora aleatória entre 8h e 20h
    hour = random.randint(8, 20)
    minute = random.randint(0, 59)
    
    return receipt_date.replace(hour=hour, minute=minute, second=0, microsecond=0)


def create_receipt(
    db,
    user: User,
    store: Dict,
    emitted_at: datetime,
    items: List[Dict],
    access_key: str
) -> Receipt:
    """Cria um receipt com seus itens."""
    
    # Calcular totais
    subtotal = sum(item["total_price"] for item in items)
    total_tax = 0.0  # Sem impostos para simplificar
    total_value = subtotal + total_tax
    
    # Criar raw_qr_text fake
    fake_qr_text = f"https://nfce.fazenda.fake/{access_key}"
    
    # Criar receipt
    receipt = Receipt(
        user_id=user.id,
        access_key=access_key,
        raw_qr_text=encrypt_sensitive_data(fake_qr_text),
        total_value=total_value,
        subtotal=subtotal,
        total_tax=total_tax,
        emitted_at=emitted_at,
        store_name=store["name"],
        store_cnpj=store["cnpj"],
    )
    db.add(receipt)
    db.flush()
    
    # Criar itens
    for item_data in items:
        # Buscar ou criar categoria
        category_id = None
        if item_data.get("category"):
            category_id = get_or_create_category(db, item_data["category"])
        
        # Criar ou buscar produto
        product_id = get_or_create_product_from_item(
            db=db,
            item={
                "description": item_data["name"],
                "barcode": None,
                "category_id": category_id
            }
        )
        
        # Criar receipt item
        receipt_item = ReceiptItem(
            receipt_id=receipt.id,
            product_id=product_id,
            description=item_data["name"],
            quantity=item_data["quantity"],
            unit_price=item_data["unit_price"],
            total_price=item_data["total_price"],
            tax_value=0.0,
        )
        db.add(receipt_item)
    
    db.commit()
    db.refresh(receipt)
    
    return receipt


def generate_receipt_items() -> List[Dict]:
    """Gera uma lista aleatória de itens para uma nota."""
    num_items = random.randint(5, 12)
    selected_products = random.sample(PRODUCTS, num_items)
    
    items = []
    for product in selected_products:
        quantity = random.randint(1, 5)
        min_price, max_price = product["base_price"]
        unit_price = round(random.uniform(min_price, max_price), 2)
        total_price = round(unit_price * quantity, 2)
        
        items.append({
            "name": product["name"],
            "quantity": quantity,
            "unit_price": unit_price,
            "total_price": total_price,
            "category": product["category"]
        })
    
    return items


def seed_data():
    """Função principal para popular o banco de dados."""
    print("=" * 60)
    print("SEED DE DADOS - ECONOMIZA BACKEND")
    print("=" * 60)
    print()
    
    db = SessionLocal()
    
    try:
        # 1. Criar ou buscar usuário
        print("[1/4] Verificando usuário...")
        user = get_or_create_user(db)
        print()
        
        # 2. Garantir que categorias existem
        print("[2/4] Verificando categorias...")
        categories_needed = set(p["category"] for p in PRODUCTS)
        for cat_name in categories_needed:
            get_or_create_category(db, cat_name)
        db.commit()
        print(f"[OK] {len(categories_needed)} categorias verificadas")
        print()
        
        # 3. Gerar notas fiscais
        print("[3/4] Gerando notas fiscais...")
        
        # 8 meses: abril a novembro de 2025
        months = [
            (2025, 4), (2025, 5), (2025, 6), (2025, 7),
            (2025, 8), (2025, 9), (2025, 10), (2025, 11)
        ]
        
        total_receipts = 0
        total_created = 0
        total_skipped = 0
        
        for year, month in months:
            print(f"  Mês {month:02d}/{year}:")
            
            # 12 notas por mês (3 por semana, 4 semanas)
            for week in range(4):  # 4 semanas
                for day_in_week in range(3):  # 3 dias por semana
                    # Selecionar mercado aleatório
                    store = random.choice(STORES)
                    
                    # Gerar data
                    emitted_at = generate_receipt_date(year, month, week, day_in_week)
                    
                    # Gerar access_key única
                    index = week * 3 + day_in_week
                    access_key = generate_access_key(store["name"], emitted_at, index)
                    
                    # Gerar itens
                    items = generate_receipt_items()
                    
                    # Verificar se já existe antes de criar
                    existing = db.query(Receipt).filter(
                        Receipt.user_id == user.id,
                        Receipt.access_key == access_key
                    ).first()
                    
                    if existing:
                        total_skipped += 1
                    else:
                        # Criar receipt
                        receipt = create_receipt(
                            db=db,
                            user=user,
                            store=store,
                            emitted_at=emitted_at,
                            items=items,
                            access_key=access_key
                        )
                        total_created += 1
                    
                    total_receipts += 1
                    
                    if total_receipts % 12 == 0:
                        print(f"    {total_receipts} notas processadas ({total_created} criadas, {total_skipped} puladas)...")
        
        print()
        print(f"[OK] Total de notas: {total_receipts}")
        print(f"[OK] Notas criadas: {total_created}")
        print(f"[OK] Notas já existentes (puladas): {total_skipped}")
        print()
        
        # 4. Resumo final
        print("[4/4] Resumo final...")
        total_receipts_db = db.query(Receipt).filter(Receipt.user_id == user.id).count()
        total_items_db = db.query(ReceiptItem).join(Receipt).filter(Receipt.user_id == user.id).count()
        total_products_db = db.query(Category).count()
        
        print(f"[OK] Receipts no banco: {total_receipts_db}")
        print(f"[OK] Receipt items no banco: {total_items_db}")
        print(f"[OK] Categorias no banco: {total_products_db}")
        print()
        
        print("=" * 60)
        print("SEED CONCLUÍDO COM SUCESSO! ✅")
        print("=" * 60)
        print()
        print("Agora você pode testar:")
        print("  - Analytics mensais: GET /api/v1/analytics/monthly-summary")
        print("  - Top itens: GET /api/v1/analytics/top-items")
        print("  - Comparação de mercados: GET /api/v1/analytics/compare-store")
        print("  - IA de economia: GET /api/v1/ai/savings-suggestions")
        print()
        
    except Exception as e:
        db.rollback()
        print(f"[ERRO] Erro ao executar seed: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_data()

