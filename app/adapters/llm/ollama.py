import logging

import httpx

from app.ports.llm import LLMPort
from app.prompts.templates import (
    ANALYZE_REVIEWS,
    SUMMARIZE_BOOK,
    render_book_summary_prompt,
    render_review_consensus_prompt,
)

logger = logging.getLogger(__name__)


class OllamaLLMAdapter(LLMPort):
    """LLM adapter using a local Ollama instance."""

    def __init__(self, base_url: str, model: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model

    async def _generate(self, system: str, user: str, max_tokens: int) -> str:
        """Send a chat completion request to Ollama."""
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        async with httpx.AsyncClient(timeout=180.0) as client:
            logger.info("Ollama request: model=%s, max_tokens=%d", self._model, max_tokens)
            resp = await client.post(f"{self._base_url}/api/chat", json=payload)
            resp.raise_for_status()
            result = resp.json()["message"]["content"]
            logger.info("Ollama response: %d chars", len(result))
            return result

    async def summarize_book(self, text: str) -> str:
        """Generate a book summary via Ollama."""
        prompt = render_book_summary_prompt(text)
        return await self._generate(
            prompt["system"], prompt["user"], SUMMARIZE_BOOK.max_tokens
        )

    async def analyze_reviews(
        self, reviews: list[dict], current_consensus: str | None
    ) -> str:
        """Generate/update review consensus via Ollama."""
        prompt = render_review_consensus_prompt(reviews, current_consensus)
        return await self._generate(
            prompt["system"], prompt["user"], ANALYZE_REVIEWS.max_tokens
        )
