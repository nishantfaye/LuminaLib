"""
Structured, reusable, versioned prompt templates for LLM interactions.

Design Principles:
  1. Prompts are immutable dataclass objects — no inline strings in adapters.
  2. Each template is versioned for traceability and A/B testing.
  3. Templates are adapter-agnostic: same template works with Ollama, OpenAI, etc.
  4. Content truncation is handled here (not in adapters) with configurable limits.
  5. Helper functions handle formatting and rendering.
"""

from dataclasses import dataclass, field


# ── Token Estimation ─────────────────────────────────────────────
# Rough estimate: 1 token ≈ 4 characters for English text.
# This avoids a tokenizer dependency while staying safe for context limits.

CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Estimate token count from character length."""
    return len(text) // CHARS_PER_TOKEN


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Truncate text to approximately max_tokens."""
    max_chars = max_tokens * CHARS_PER_TOKEN
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    # Cut at the last sentence boundary to avoid mid-sentence truncation
    last_period = truncated.rfind(".")
    if last_period > max_chars * 0.8:
        truncated = truncated[: last_period + 1]
    return truncated + "\n\n[Content truncated for processing]"


# ── Prompt Template ──────────────────────────────────────────────

@dataclass(frozen=True)
class PromptTemplate:
    """
    Immutable prompt template with system persona and user message.

    Attributes:
        name:              Unique identifier for logging and tracking.
        version:           Semantic version for prompt iteration tracking.
        system:            System message defining the LLM persona and constraints.
        user_template:     User message template with {variable} placeholders.
        max_tokens:        Maximum output tokens requested from the LLM.
        input_token_limit: Maximum tokens for input content (prevents context overflow).
        tags:              Metadata tags for categorization.
    """

    name: str
    version: str
    system: str
    user_template: str
    max_tokens: int = 1024
    input_token_limit: int = 4000
    tags: tuple[str, ...] = field(default_factory=tuple)

    def render(self, **kwargs: str) -> dict[str, str]:
        """Render template with variables, returning system + user messages."""
        return {
            "system": self.system,
            "user": self.user_template.format(**kwargs),
        }

    def render_with_truncation(self, content_key: str, **kwargs: str) -> dict[str, str]:
        """Render template, truncating the specified content field to fit token limits."""
        if content_key in kwargs:
            kwargs[content_key] = truncate_to_tokens(
                kwargs[content_key], self.input_token_limit
            )
        return self.render(**kwargs)


# ── Book Summarization Prompt ────────────────────────────────────

SUMMARIZE_BOOK = PromptTemplate(
    name="summarize_book",
    version="1.2.0",
    system=(
        "You are a skilled literary analyst working for a digital library system. "
        "Your role is to produce clear, informative book summaries suitable for a "
        "library catalog.\n\n"
        "Guidelines:\n"
        "- Write 3-5 concise paragraphs.\n"
        "- Cover main themes, structure, and key arguments or plot points.\n"
        "- Do NOT include spoilers for fiction.\n"
        "- Use a neutral, professional tone.\n"
        "- Mention who would benefit most from reading this book.\n"
        "- If the content appears to be partial or corrupted, note this clearly."
    ),
    user_template=(
        "Please summarize the following book content.\n\n"
        "--- BOOK CONTENT (START) ---\n"
        "{content}\n"
        "--- BOOK CONTENT (END) ---\n\n"
        "Provide a comprehensive summary in 3-5 paragraphs:"
    ),
    max_tokens=1024,
    input_token_limit=4000,
    tags=("summarization", "book", "ingestion"),
)


# ── Review Consensus Prompt ──────────────────────────────────────

ANALYZE_REVIEWS = PromptTemplate(
    name="analyze_reviews",
    version="1.1.0",
    system=(
        "You are a sentiment analysis expert specializing in literary reviews. "
        "Your task is to synthesize multiple reader opinions into a balanced, "
        "nuanced consensus.\n\n"
        "Guidelines:\n"
        "- Produce 2-3 paragraphs.\n"
        "- Identify areas of agreement and disagreement among reviewers.\n"
        "- Note the overall sentiment (positive, mixed, negative) with nuance.\n"
        "- Highlight commonly praised strengths and commonly cited weaknesses.\n"
        "- Conclude with who would likely enjoy this book.\n"
        "- If a previous consensus exists, update it — don't start from scratch."
    ),
    user_template=(
        "{previous_consensus_section}"
        "Below are reader reviews for this book:\n\n"
        "--- REVIEWS (START) ---\n"
        "{reviews_text}\n"
        "--- REVIEWS (END) ---\n\n"
        "Synthesize these into an updated consensus summary:"
    ),
    max_tokens=512,
    input_token_limit=3000,
    tags=("sentiment", "reviews", "consensus"),
)


# ── Rendering Helpers ────────────────────────────────────────────

def render_book_summary_prompt(content: str) -> dict[str, str]:
    """Render the book summarization prompt with safe truncation."""
    return SUMMARIZE_BOOK.render_with_truncation(
        content_key="content",
        content=content,
    )


def render_review_consensus_prompt(
    reviews: list[dict],
    current_consensus: str | None = None,
) -> dict[str, str]:
    """
    Render the review consensus prompt.

    Args:
        reviews: List of dicts with 'rating' (int) and 'text' (str) keys.
        current_consensus: Existing consensus text to update, or None.

    Returns:
        Dict with 'system' and 'user' keys ready for any LLM adapter.
    """
    reviews_text = "\n\n".join(
        f"[Rating: {r['rating']}/5]\n{r['text']}" for r in reviews
    )

    previous_section = ""
    if current_consensus:
        previous_section = (
            "--- PREVIOUS CONSENSUS (START) ---\n"
            f"{current_consensus}\n"
            "--- PREVIOUS CONSENSUS (END) ---\n\n"
            "Update the above consensus with the new reviews below.\n\n"
        )

    return ANALYZE_REVIEWS.render_with_truncation(
        content_key="reviews_text",
        reviews_text=reviews_text,
        previous_consensus_section=previous_section,
    )


# ── Prompt Registry ──────────────────────────────────────────────
# Central registry for discoverability, logging, and future API exposure.

PROMPT_REGISTRY: dict[str, PromptTemplate] = {
    SUMMARIZE_BOOK.name: SUMMARIZE_BOOK,
    ANALYZE_REVIEWS.name: ANALYZE_REVIEWS,
}


def get_prompt(name: str) -> PromptTemplate:
    """Retrieve a prompt template by name. Raises KeyError if not found."""
    if name not in PROMPT_REGISTRY:
        raise KeyError(
            f"Prompt '{name}' not found. Available: {list(PROMPT_REGISTRY.keys())}"
        )
    return PROMPT_REGISTRY[name]
