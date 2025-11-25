"""
Script para iniciar o worker do Celery
Uso: celery -A celery_worker worker --loglevel=info
"""
from app.celery_app import celery_app

if __name__ == "__main__":
    celery_app.start()

