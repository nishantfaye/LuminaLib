import logging

from openai import AsyncOpenAI

from app.ports.llm import LLMPort
from app.prompts.templates import (
    ANALYZE_REVIEWS,
    SUMMARIZE_BOOK,
    render_book_summary_prompt,
    render_review_consensus_prompt,
)

logger = logging.getLogger(__name__)


class OpenAILLMAdapter(LLMPort):
    """LLM adapter using OpenAI API (GPT-4o, GPT-4o-mini, etc.)."""

    def __init__(self, api_key: str, model: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def _generate(self, system: str, user: str, max_tokens: int) -> str:
        """Send a chat completion request to OpenAI."""
        logger.info("OpenAI request: model=%s, max_tokens=%d", self._model, max_tokens)
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
            temperature=0.7,
        )
        result = resp.choices[0].message.content or ""
        logger.info("OpenAI response: %d chars", len(result))
        return result

    async def summarize_book(self, text: str) -> str:
        """Generate a book summary via OpenAI."""
        prompt = render_book_summary_prompt(text)
        return await self._generate(
            prompt["system"], prompt["user"], SUMMARIZE_BOOK.max_tokens
        )

    async def analyze_reviews(
        self, reviews: list[dict], current_consensus: str | None
    ) -> str:
        """Generate/update review consensus via OpenAI."""
        prompt = render_review_consensus_prompt(reviews, current_consensus)
        return await self._generate(
            prompt["system"], prompt["user"], ANALYZE_REVIEWS.max_tokens
        )
