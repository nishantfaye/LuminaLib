"""Review submission service with borrow constraint enforcement."""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import ReviewCreateRequest
from app.domain.models import Borrow, Review, UserInteraction


class ReviewService:
    """Handles review creation with borrow validation."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_review(
        self, book_id: UUID, user_id: UUID, data: ReviewCreateRequest
    ) -> Review:
        """
        Submit a review for a book.

        Constraint: The user must have borrowed the book (active or returned).
        Raises 403 if the user has never borrowed this book.
        """
        borrow_result = await self._session.execute(
            select(Borrow).where(
                Borrow.book_id == book_id,
                Borrow.user_id == user_id,
            )
        )
        if not borrow_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You must borrow a book before reviewing it",
            )

        review = Review(
            user_id=user_id,
            book_id=book_id,
            rating=data.rating,
            text=data.text,
        )
        self._session.add(review)

        interaction = UserInteraction(
            user_id=user_id,
            book_id=book_id,
            interaction_type="review",
            rating=float(data.rating),
        )
        self._session.add(interaction)
        await self._session.flush()
        return review

    async def get_reviews_for_book(self, book_id: UUID) -> list[Review]:
        """Retrieve all reviews for a specific book."""
        result = await self._session.execute(
            select(Review)
            .where(Review.book_id == book_id)
            .order_by(Review.created_at.desc())
        )
        return list(result.scalars().all())
