from typing import Annotated, Any, AsyncGenerator, Dict, Optional
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.session import get_async_db
from app.models.entities import Reviewer


async def get_current_reviewer_claims(
    authorization: Optional[str] = Header(None, description="Bearer <JWT_TOKEN>"),
) -> dict[str, Any]:
    """Validate JWT token from Authorization header and return claims."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.split(" ", 1)[1]
    try:
        payload = decode_access_token(token)
        if "sub" not in payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token payload missing subject identifier",
            )
        return payload
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication token invalid or expired: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_reviewer(
    claims: Annotated[dict[str, Any], Depends(get_current_reviewer_claims)],
    db: Annotated[AsyncSession, Depends(get_async_db)],
) -> Reviewer:
    """Fetch current authenticated Reviewer from database."""
    reviewer_id = int(claims["sub"])
    stmt = select(Reviewer).where(Reviewer.id == reviewer_id)
    result = await db.execute(stmt)
    reviewer = result.scalar_one_or_none()

    if not reviewer:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Reviewer account not found",
        )
    return reviewer
