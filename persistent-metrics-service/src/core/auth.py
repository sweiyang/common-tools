import secrets

from fastapi import Header, HTTPException, status

from src.core.config import get_settings


async def verify_api_key(x_api_key: str = Header(...)) -> str:
    expected = get_settings().auth.api_key
    if not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return x_api_key
