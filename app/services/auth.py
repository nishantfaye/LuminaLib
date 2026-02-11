"""Authentication and user lifecycle service."""

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.middleware.auth import create_access_token, hash_password, verify_password
from app.api.schemas import SignupRequest
from app.domain.models import User


class AuthService:
    """Handles user registration, authentication, and profile retrieval."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def signup(self, data: SignupRequest) -> User:
        """Register a new user. Raises 409 if email or username exists."""
        existing = await self._session.execute(
            select(User).where(
                or_(User.email == data.email, User.username == data.username)
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email or username already registered",
            )

        user = User(
            email=data.email,
            username=data.username,
            hashed_password=hash_password(data.password),
        )
        self._session.add(user)
        await self._session.flush()
        return user

    async def login(self, email: str, password: str) -> str:
        """Authenticate user and return a JWT access token."""
        result = await self._session.execute(
            select(User).where(User.email == email)
        )
        user = result.scalar_one_or_none()

        if not user or not verify_password(password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )

        return create_access_token(user.id)
