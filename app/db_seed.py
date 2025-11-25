"""
Script de seed para criar usuário de desenvolvimento no banco de dados.
"""
import sys
import os
from uuid import UUID
from datetime import datetime

# Adicionar o diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.database import SessionLocal
from app.models.user import User

# UUID do usuário de desenvolvimento (deve corresponder ao usado em app/dependencies/auth.py)
DEV_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


def create_dev_user():
    """Cria o usuário de desenvolvimento se não existir."""
    db = SessionLocal()
    
    try:
        # Verificar se o usuário já existe
        existing_user = db.query(User).filter(User.id == DEV_USER_ID).first()
        
        if existing_user:
            print(f"[OK] Usuario de desenvolvimento ja existe: {existing_user.email} (ID: {existing_user.id})")
            return
        
        # Criar novo usuário de desenvolvimento
        dev_user = User(
            id=DEV_USER_ID,
            email="dev@example.com",
            password_hash="dev",  # Hash simples para desenvolvimento
            consent_given=True,
            consent_terms=True,
            is_pro=False,
            subscription_id=None,
            stripe_customer_id=None,
            deleted_at=None,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        db.add(dev_user)
        db.commit()
        db.refresh(dev_user)
        
        print(f"[OK] Usuario de desenvolvimento criado com sucesso!")
        print(f"  ID: {dev_user.id}")
        print(f"  Email: {dev_user.email}")
        print(f"  Consent: {dev_user.consent_given}")
        print(f"  Is PRO: {dev_user.is_pro}")
        
    except Exception as e:
        db.rollback()
        print(f"[ERRO] Erro ao criar usuario de desenvolvimento: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("Criando usuário de desenvolvimento...")
    create_dev_user()

