"""
Script para testar a conexão com o banco de dados Supabase
"""
from app.database import engine
from sqlalchemy import text


def test_connection():
    """Testa a conexão com o banco de dados"""
    try:
        print("Testando conexão com o banco de dados...")
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))
            row = result.fetchone()
            if row and row[0] == 1:
                print("✅ Conexão com o banco de dados estabelecida com sucesso!")
                return True
            else:
                print("❌ Erro: Resposta inesperada do banco de dados")
                return False
    except Exception as e:
        print(f"❌ Erro ao conectar com o banco de dados: {str(e)}")
        return False


if __name__ == "__main__":
    test_connection()

