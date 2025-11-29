from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import httpx
from jose import jwt
import os

bearer = HTTPBearer()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_JWKS_URL = os.getenv("SUPABASE_JWKS_URL")
SUPABASE_AUDIENCE = os.getenv("SUPABASE_AUDIENCE", "authenticated")
DEV_MODE = os.getenv("DEV_MODE", "true").lower() == "true"

JWKS_CACHE = None


async def get_jwks():
    global JWKS_CACHE
    if JWKS_CACHE:
        return JWKS_CACHE

    async with httpx.AsyncClient() as client:
        r = await client.get(SUPABASE_JWKS_URL, timeout=10)
        r.raise_for_status()
        JWKS_CACHE = r.json()
        return JWKS_CACHE


async def validate_token(token: str):
    if DEV_MODE:
        return {"sub": "dev-user", "email": "dev@local"}

    jwks = await get_jwks()
    unverified = jwt.get_unverified_header(token)

    for key in jwks["keys"]:
        if key["kid"] == unverified["kid"]:
            return jwt.decode(
                token,
                key,
                audience=SUPABASE_AUDIENCE,
                algorithms=["RS256"]
            )

    raise HTTPException(status_code=401, detail="Invalid token")


async def get_current_user(credentials: HTTPAuthorizationCredentials = Security(bearer)):
    token = credentials.credentials
    if not token:
        raise HTTPException(401, "Authorization header missing")
    payload = await validate_token(token)
    return payload
