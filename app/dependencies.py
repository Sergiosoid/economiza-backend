"""
Dependências do FastAPI
"""
from fastapi import Header, HTTPException
from typing import Optional
from uuid import UUID
import logging

logger = logging.getLogger(__name__)


# TODO: Substituir por autenticação JWT real
async def get_current_user(authorization: Optional[str] = Header(None)) -> UUID:
    """
    Stub de autenticação para testes.
    Aceita qualquer token no formato 'Bearer <token>' e retorna um user_id fixo.
    Em produção, deve validar JWT e extrair user_id do token.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header missing")
    
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization format")
    
    token = authorization.replace("Bearer ", "").strip()
    
    # Para testes: aceita qualquer token e retorna um UUID fixo
    # Em produção, validar JWT e extrair user_id
    if token:
        # UUID fixo para testes - em produção virá do JWT
        test_user_id = UUID("00000000-0000-0000-0000-000000000001")
        logger.info(f"Authenticated user (stub): {test_user_id}")
        return test_user_id
    
    raise HTTPException(status_code=401, detail="Invalid token")

