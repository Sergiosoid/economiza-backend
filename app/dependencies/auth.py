from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from uuid import UUID
import logging
from app.database import get_db
from app.models.user import User
from app.config import settings
from app.services.supabase_auth import validate_token

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)


def parse_raw_auth_header(request: Request) -> Optional[str]:
    """Retorna o token puro caso Authorization não siga o esquema 'Bearer <token>'."""
    header = request.headers.get("authorization")
    if not header:
        return None
    header = header.strip()
    # header pode ser "Bearer token", "bearer token" ou só "token"
    parts = header.split()
    if len(parts) == 1:
        return parts[0]
    if len(parts) >= 2:
        # usar a segunda parte como token
        return parts[1]
    return None


def get_or_create_user_from_supabase(
    db: Session,
    supabase_sub: str,
    email: str
) -> User:
    """
    Busca ou cria usuário baseado no token do Supabase.
    
    Args:
        db: Sessão do banco de dados
        supabase_sub: ID do usuário no Supabase (sub do JWT)
        email: Email do usuário
        
    Returns:
        User: Usuário encontrado ou criado
    """
    # Tentar buscar por email primeiro
    user = db.query(User).filter(
        User.email == email,
        User.deleted_at.is_(None)
    ).first()
    
    if user:
        logger.debug(f"User found by email: {user.id}")
        return user
    
    # Se não encontrou, criar novo usuário
    # Usar o sub do Supabase como base para o UUID (ou gerar novo)
    try:
        # Tentar converter sub para UUID se possível
        user_id = UUID(supabase_sub) if len(supabase_sub) == 36 else None
    except (ValueError, AttributeError):
        user_id = None
    
    if not user_id:
        # Gerar novo UUID
        import uuid
        user_id = uuid.uuid4()
    
    user = User(
        id=user_id,
        email=email,
        password_hash="supabase_auth",  # Placeholder, não usado com Supabase Auth
        consent_given=False,
        consent_terms=False,
        is_pro=False,
    )
    
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # Em modo DEV, setar consentimento automaticamente
    if settings.DEV_MODE:
        user.consent_given = True
        user.consent_terms = True  # Boolean: True indica consentimento automático em DEV
        db.commit()
        db.refresh(user)
        logger.info(f"Auto-consent applied (DEV_MODE): user_id={user.id}")
    
    logger.info(f"User created from Supabase token: {user.id} ({email})")
    return user


async def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    cred: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> UUID:
    """
    Dependência para rotas que precisam de autenticação.
    - Aceita 'Authorization: Bearer <token>' (padrão)
    - Aceita 'Authorization: <token>' (somente token)
    - Aceita variações de case (Bearer/bearer)
    - Ambiente dev aceita token 'test' (se DEV_MODE=true)
    - Valida token Supabase JWT e cria/busca usuário
    """
    token = None
    if cred:
        token = cred.credentials
    else:
        token = parse_raw_auth_header(request)

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing"
        )

    # Ambiente de desenvolvimento: token de teste "test"
    if settings.DEV_MODE and token == "test":
        # Buscar ou criar usuário de dev
        test_user = db.query(User).filter(
            User.email == "dev@example.com"
        ).first()
        
        if not test_user:
            # Criar usuário de dev se não existir
            test_user_id = UUID("00000000-0000-0000-0000-000000000001")
            test_user = User(
                id=test_user_id,
                email="dev@example.com",
                password_hash="dev",
                consent_given=True,
                consent_terms=True,
                is_pro=False,
            )
            db.add(test_user)
            db.commit()
            db.refresh(test_user)
        
        logger.info(f"Authenticated user (dev token): {test_user.id}")
        return test_user.id

    # Validar token Supabase JWT
    try:
        payload = await validate_token(token)
        
        # Extrair informações do payload
        supabase_sub = payload.get("sub")
        email = payload.get("email")
        
        if not supabase_sub:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing 'sub' claim"
            )
        
        if not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing 'email' claim"
            )
        
        # Buscar ou criar usuário
        user = get_or_create_user_from_supabase(db, supabase_sub, email)
        
        logger.info(f"Authenticated user (Supabase): {user.id} ({email})")
        return user.id
        
    except HTTPException:
        # Re-raise HTTPException diretamente
        raise
    except Exception as e:
        logger.error(f"Unexpected error during authentication: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed"
        )

