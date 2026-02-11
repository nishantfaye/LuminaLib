import asyncio
import logging

from app.ports.llm import LLMPort
from app.prompts.templates import estimate_tokens

logger = logging.getLogger(__name__)


class MockLLMAdapter(LLMPort):
    """
    Mock LLM adapter for testing without GPU or API access.

    Returns deterministic, realistic placeholder responses.
    Simulates realistic latency for integration testing.
    """

    async def summarize_book(self, text: str) -> str:
        """Return a mock book summary."""
        await asyncio.sleep(0.5)  # simulate LLM latency
        token_count = estimate_tokens(text)
        logger.info("MockLLM: summarize_book called (%d estimated tokens)", token_count)
        return (
            f"This book contains approximately {len(text.split())} words across "
            f"its content (estimated {token_count} tokens). "
            "It explores compelling themes through well-structured prose, presenting "
            "arguments that build methodically from foundational concepts to complex "
            "conclusions.\n\n"
            "The author demonstrates deep expertise in the subject matter, weaving "
            "together narrative elements with analytical insights. Key themes include "
            "the interplay between theory and practice, the evolution of ideas over "
            "time, and their practical implications for readers.\n\n"
            "This work is recommended for both casual readers seeking an accessible "
            "introduction and scholars looking for a comprehensive reference. The "
            "writing style balances academic rigor with engaging readability."
        )

    async def analyze_reviews(
        self, reviews: list[dict], current_consensus: str | None
    ) -> str:
        """Return a mock review consensus."""
        await asyncio.sleep(0.3)  # simulate LLM latency
        count = len(reviews)
        avg = sum(r["rating"] for r in reviews) / count if count else 0.0

        if avg >= 4.0:
            sentiment = "overwhelmingly positive"
        elif avg >= 3.0:
            sentiment = "generally positive with some reservations"
        elif avg >= 2.0:
            sentiment = "mixed, with both praise and criticism"
        else:
            sentiment = "predominantly critical"

        logger.info(
            "MockLLM: analyze_reviews called (%d reviews, avg=%.1f)", count, avg
        )
        return (
            f"Based on {count} reader reviews with an average rating of {avg:.1f}/5, "
            f"the overall sentiment is {sentiment}.\n\n"
            "Reviewers commonly praise the depth of content and quality of writing. "
            "Some readers note that certain sections require careful attention, while "
            "others appreciate the thoroughness of the coverage. The book's structure "
            "receives generally positive feedback.\n\n"
            "This book is recommended for readers with a genuine interest in the "
            "subject matter who appreciate detailed, well-researched content."
        )
