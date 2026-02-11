"""Intelligence & recommendation routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.recommender.hybrid import HybridRecommenderAdapter
from app.api.middleware.auth import get_current_user
from app.api.schemas import (
    AnalysisResponse,
    PreferencesRequest,
    PreferencesResponse,
    RecommendationItem,
    RecommendationsResponse,
)
from app.config import settings
from app.database import async_session_factory, get_session
from app.domain.models import Book, Review, User, UserPreference

router = APIRouter(tags=["Intelligence"])


@router.get("/books/{book_id}/analysis", response_model=AnalysisResponse)
async def get_analysis(
    book_id: UUID,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> AnalysisResponse:
    """Get GenAI-aggregated summary of all reviews for a book."""
    result = await session.execute(select(Book).where(Book.id == book_id))
    book = result.scalar_one_or_none()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    stats = await session.execute(
        select(
            func.count(Review.id).label("total"),
            func.avg(Review.rating).label("avg_rating"),
        ).where(Review.book_id == book_id)
    )
    row = stats.one()

    return AnalysisResponse(
        book_id=book.id,
        summary=book.summary,
        review_consensus=book.review_consensus,
        total_reviews=row.total or 0,
        average_rating=round(float(row.avg_rating), 2) if row.avg_rating else None,
    )


@router.get("/recommendations", response_model=RecommendationsResponse)
async def get_recommendations(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> RecommendationsResponse:
    """Get ML-based personalized book suggestions for the current user."""
    recommender = HybridRecommenderAdapter(
        session_factory=async_session_factory,
        alpha=settings.recommendation_alpha,
    )
    results = await recommender.recommend(user.id, limit=10)

    items: list[RecommendationItem] = []
    for rec in results:
        book_result = await session.execute(
            select(Book).where(Book.id == rec.book_id)
        )
        book = book_result.scalar_one_or_none()
        if book:
            items.append(
                RecommendationItem(
                    book_id=book.id,
                    title=book.title,
                    author=book.author,
                    score=rec.score,
                    reason=rec.reason,
                )
            )

    return RecommendationsResponse(recommendations=items)


@router.put("/preferences", response_model=PreferencesResponse)
async def update_preferences(
    data: PreferencesRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> PreferencesResponse:
    """Update user's explicit genre/author preferences for recommendations."""
    result = await session.execute(
        select(UserPreference).where(UserPreference.user_id == user.id)
    )
    prefs = result.scalar_one_or_none()

    if prefs:
        prefs.favorite_genres = data.favorite_genres
        prefs.favorite_authors = data.favorite_authors
    else:
        prefs = UserPreference(
            user_id=user.id,
            favorite_genres=data.favorite_genres,
            favorite_authors=data.favorite_authors,
        )
        session.add(prefs)

    await session.flush()
    return PreferencesResponse.model_validate(prefs)
