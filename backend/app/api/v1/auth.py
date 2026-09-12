from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_reviewer, get_async_db
from app.core.security import create_access_token, verify_password
from app.models.entities import Reviewer
from app.schemas.observation import ReviewerLoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    login_req: ReviewerLoginRequest,
    db: Annotated[AsyncSession, Depends(get_async_db)],
) -> TokenResponse:
    """Authenticate reviewer using email & bcrypt hashed password, returning JWT access token."""
    stmt = select(Reviewer).where(Reviewer.email == login_req.email)
    result = await db.execute(stmt)
    reviewer = result.scalar_one_or_none()

    if not reviewer or not verify_password(login_req.password, reviewer.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    claims = {
        "email": reviewer.email,
        "role": reviewer.role,
    }
    token = create_access_token(subject=reviewer.id, claims=claims)

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        reviewer={
            "id": reviewer.id,
            "email": reviewer.email,
            "role": reviewer.role,
        },
    )


@router.get("/me")
async def get_me(
    reviewer: Annotated[Reviewer, Depends(get_current_reviewer)],
) -> dict:
    """Get authenticated reviewer info."""
    return {
        "id": reviewer.id,
        "email": reviewer.email,
        "role": reviewer.role,
        "created_at": reviewer.created_at,
    }
