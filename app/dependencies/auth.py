from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from uuid import UUID
import logging

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


async def get_current_user(
    request: Request,
    cred: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> UUID:
    """
    Dependência para rotas que precisam de autenticação.
    - Aceita 'Authorization: Bearer <token>' (padrão)
    - Aceita 'Authorization: <token>' (somente token)
    - Aceita variações de case (Bearer/bearer)
    - Ambiente dev aceita token 'test'
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
    if token == "test":
        # retornar UUID fixo para testes
        test_user_id = UUID("00000000-0000-0000-0000-000000000001")
        logger.info(f"Authenticated user (dev token): {test_user_id}")
        return test_user_id

    # Aqui você pode adicionar a validação real do token JWT no futuro
    # Exemplo (comentado): decode_jwt(token) ...

    # Se token inválido:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials"
    )

