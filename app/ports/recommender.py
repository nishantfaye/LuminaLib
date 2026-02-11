"""Recommender port — abstract interface for the recommendation engine."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID


@dataclass
class RecommendationResult:
    """A single recommendation with score and explanation."""

    book_id: UUID
    score: float
    reason: str


class RecommenderPort(ABC):
    """Abstraction for the book recommendation engine."""

    @abstractmethod
    async def recommend(
        self,
        user_id: UUID,
        limit: int = 10,
    ) -> list[RecommendationResult]:
        """Return ranked book recommendations for a user."""
        ...
