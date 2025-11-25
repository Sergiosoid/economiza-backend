"""
Seed para inserir categorias padrão no banco de dados
"""
from app.database import SessionLocal
from app.models.category import Category


def seed_categories():
    """Insere categorias padrão se elas não existirem"""
    db = SessionLocal()
    try:
        default_categories = [
            "Alimentos",
            "Higiene",
            "Limpeza",
            "Bebidas",
            "Mercearia",
            "Padaria",
            "Frios",
        ]

        for category_name in default_categories:
            # Verifica se a categoria já existe
            existing = db.query(Category).filter(Category.name == category_name).first()
            if not existing:
                category = Category(name=category_name)
                db.add(category)
                print(f"✅ Categoria '{category_name}' criada")
            else:
                print(f"⏭️  Categoria '{category_name}' já existe")

        db.commit()
        print("✅ Seed de categorias concluído com sucesso!")
    except Exception as e:
        db.rollback()
        print(f"❌ Erro ao executar seed: {str(e)}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_categories()

