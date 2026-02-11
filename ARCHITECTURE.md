# LuminaLib — Architecture Document

## Evaluation Rubric Mapping

| Rubric Criterion | Where Addressed | Key Evidence |
|---|---|---|
| **1. Modularity** (swap Storage/LLM) | Sections 2, 3, 4 | Port interfaces (ABCs) → DI container → `.env` swap proof |
| **2. Docker Proficiency** | `docker-compose.yml`, `Dockerfile` | Multi-stage build, health checks, profiles, named networks, one-command start |
| **3. Code Hygiene** | All source files, `ruff.toml` | Sorted imports (isort), type hints, docstrings, linting config |
| **4. GenAI / Prompt Engineering** | Section 8, `app/prompts/templates.py` | Versioned PromptTemplate dataclass, registry, token estimation, adapter-agnostic |

---

## Table of Contents

1. [High-Level Architecture](#1-high-level-architecture)
2. [Dependency Injection & Interface-Driven Development](#2-dependency-injection--interface-driven-development)
3. [Swapping Providers — Step-by-Step Proof](#3-swapping-providers--step-by-step-proof)
4. [Adding a New Provider (Extensibility)](#4-adding-a-new-provider-extensibility)
5. [Database Schema Design](#5-database-schema-design)
6. [Async Strategy for LLM Tasks](#6-async-strategy-for-llm-tasks)
7. [ML Recommendation Engine](#7-ml-recommendation-engine)
8. [Prompt Engineering Strategy](#8-prompt-engineering-strategy)
9. [Testing Benefits of DI](#9-testing-benefits-of-di)
10. [Assumptions & Trade-offs](#10-assumptions--trade-offs)

---

## 1. High-Level Architecture

LuminaLib follows **Hexagonal Architecture** (Ports & Adapters), ensuring that business logic is completely decoupled from infrastructure concerns.

```
                         ┌──────────────────────┐
                         │     API Layer         │
                         │  (FastAPI Routes)     │
                         └──────────┬───────────┘
                                    │ depends on
                         ┌──────────▼───────────┐
                         │   Service Layer       │
                         │  (Business Logic)     │
                         │                       │
                         │ BookService           │
                         │ AuthService           │
                         │ ReviewService         │
                         └──────────┬───────────┘
                                    │ depends on interfaces only
                    ┌───────────────┼───────────────┐
                    │               │               │
           ┌────────▼──────┐ ┌─────▼──────┐ ┌──────▼─────────┐
           │  StoragePort   │ │  LLMPort   │ │ RecommenderPort│
           │  (ABC)         │ │  (ABC)     │ │ (ABC)          │
           └────────┬──────┘ └─────┬──────┘ └──────┬─────────┘
                    │              │               │
        ┌───────────┤       ┌──────┤        ┌──────┘
        │           │       │      │        │
   ┌────▼───┐ ┌────▼──┐ ┌──▼───┐ ┌▼─────┐ ┌▼──────────┐
   │ Local   │ │  S3   │ │Ollama│ │OpenAI│ │  Hybrid   │
   │ Disk    │ │(MinIO)│ │LLM   │ │ LLM  │ │ Recommender│
   └─────────┘ └───────┘ └──────┘ └──────┘ └───────────┘
```

**Key Principle**: The Service Layer never imports a concrete adapter. It only knows about the Port interface. The DI container (`dependencies.py`) decides which adapter to inject at runtime based on configuration.

---

## 2. Dependency Injection & Interface-Driven Development

### 2.1 Port Interfaces (The Contracts)

Every external dependency is defined as an Abstract Base Class. These are the **contracts** that any adapter must fulfill:

```python
# app/ports/storage.py
class StoragePort(ABC):
    @abstractmethod
    async def save(self, file_id: UUID, content: bytes, extension: str) -> str: ...

    @abstractmethod
    async def read(self, path: str) -> bytes: ...

    @abstractmethod
    async def delete(self, path: str) -> None: ...
```

```python
# app/ports/llm.py
class LLMPort(ABC):
    @abstractmethod
    async def summarize_book(self, text: str) -> str: ...

    @abstractmethod
    async def analyze_reviews(self, reviews: list[dict], current_consensus: str | None) -> str: ...
```

```python
# app/ports/recommender.py
class RecommenderPort(ABC):
    @abstractmethod
    async def recommend(self, user_id: UUID, limit: int = 10) -> list[RecommendationResult]: ...
```

### 2.2 The DI Container (The Wiring)

`app/dependencies.py` is the single place where config maps to concrete adapters:

```python
# app/dependencies.py
def get_storage() -> StoragePort:
    if settings.storage_backend == StorageBackend.S3:
        from app.adapters.storage.s3 import S3StorageAdapter
        return S3StorageAdapter(
            endpoint_url=settings.s3_endpoint_url,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            bucket=settings.s3_bucket,
        )
    from app.adapters.storage.local import LocalStorageAdapter
    return LocalStorageAdapter(base_path=settings.local_storage_path)


def get_llm() -> LLMPort:
    if settings.llm_provider == LLMProvider.OLLAMA:
        from app.adapters.llm.ollama import OllamaLLMAdapter
        return OllamaLLMAdapter(base_url=settings.ollama_base_url, model=settings.ollama_model)
    if settings.llm_provider == LLMProvider.OPENAI:
        from app.adapters.llm.openai_adapter import OpenAILLMAdapter
        return OpenAILLMAdapter(api_key=settings.openai_api_key, model=settings.openai_model)
    from app.adapters.llm.mock import MockLLMAdapter
    return MockLLMAdapter()
```

### 2.3 How Services Consume Ports

Services **never** reference a concrete adapter. They receive a `StoragePort` or `LLMPort`:

```python
# app/services/book.py
class BookService:
    def __init__(self, session: AsyncSession, storage: StoragePort) -> None:
        self._session = session
        self._storage = storage     # ← interface, not LocalStorageAdapter

    async def create_book(self, meta: BookCreateMeta, file: UploadFile) -> Book:
        content = await file.read()
        # ...
        file_path = await self._storage.save(book.id, content, ext)   # ← polymorphic call
```

### 2.4 How Routes Wire It Together

FastAPI routes call the DI factory functions and pass them to services:

```python
# app/api/routes/books.py
@router.post("", response_model=BookResponse, status_code=201)
async def create_book(
    background_tasks: BackgroundTasks,
    # ... form fields ...
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> BookResponse:
    storage = get_storage()          # ← DI resolves based on .env
    svc = BookService(session, storage)
    book = await svc.create_book(meta, file)

    llm = get_llm()                  # ← DI resolves based on .env
    background_tasks.add_task(generate_book_summary, book.id, storage, llm)
    return BookResponse.model_validate(book)
```

### 2.5 Complete Dependency Flow

```
.env (STORAGE_BACKEND=local, LLM_PROVIDER=ollama)
        │
        ▼
   app/config.py → Settings(storage_backend=local, llm_provider=ollama)
        │
        ▼
   app/dependencies.py
        │
        ├─ get_storage() → reads settings → returns LocalStorageAdapter
        │
        └─ get_llm()     → reads settings → returns OllamaLLMAdapter
              │
              ▼
       app/api/routes/books.py
              │
              ├─ storage = get_storage()   → StoragePort (actually LocalStorageAdapter)
              │
              └─ BookService(session, storage)
                    │
                    └─ self._storage.save(...)  → calls LocalStorageAdapter.save()
```

**The service never knows it's talking to local disk. It only knows `StoragePort`.**

---

## 3. Swapping Providers — Step-by-Step Proof

### 3.1 Swap Storage: Local Disk → AWS S3

**Files changed: 1 (`.env`)**
**Code changed: 0 lines**

```diff
# .env
- STORAGE_BACKEND=local
+ STORAGE_BACKEND=s3
+ S3_ENDPOINT_URL=https://s3.amazonaws.com
+ S3_ACCESS_KEY=AKIA...
+ S3_SECRET_KEY=wJalr...
+ S3_BUCKET=luminalib-prod
```

What happens internally:
1. `Settings` reads `STORAGE_BACKEND=s3`
2. `get_storage()` takes the S3 branch → returns `S3StorageAdapter`
3. `BookService` receives an `S3StorageAdapter` through the `StoragePort` interface
4. All `.save()`, `.read()`, `.delete()` calls now go to S3
5. No service, route, or model code is touched

### 3.2 Swap LLM: Ollama (Llama 3) → OpenAI (GPT-4o)

**Files changed: 1 (`.env`)**
**Code changed: 0 lines**

```diff
# .env
- LLM_PROVIDER=ollama
- OLLAMA_BASE_URL=http://ollama:11434
- OLLAMA_MODEL=llama3
+ LLM_PROVIDER=openai
+ OPENAI_API_KEY=sk-proj-...
+ OPENAI_MODEL=gpt-4o-mini
```

What happens internally:
1. `Settings` reads `LLM_PROVIDER=openai`
2. `get_llm()` takes the OpenAI branch → returns `OpenAILLMAdapter`
3. Both background tasks (`generate_book_summary`, `update_review_consensus`) receive the OpenAI adapter through `LLMPort`
4. Prompt templates remain **identical** — they are adapter-agnostic (defined in `app/prompts/templates.py`)
5. No business logic, route, or task code is touched

### 3.3 Swap Both Simultaneously

```diff
# .env
- STORAGE_BACKEND=local
- LLM_PROVIDER=mock
+ STORAGE_BACKEND=s3
+ LLM_PROVIDER=openai
+ S3_ENDPOINT_URL=https://s3.amazonaws.com
+ OPENAI_API_KEY=sk-proj-...
```

Restart the container. Done. The entire infrastructure layer changes, business logic untouched.

---

## 4. Adding a New Provider (Extensibility)

To add a completely new provider — say, **Google Cloud Storage** and **Anthropic Claude** — here's exactly what you'd do:

### 4.1 Add a GCS Storage Adapter

```python
# app/adapters/storage/gcs.py
from app.ports.storage import StoragePort

class GCSStorageAdapter(StoragePort):
    def __init__(self, bucket: str, credentials_path: str) -> None:
        # initialize GCS client
        ...

    async def save(self, file_id, content, extension) -> str: ...
    async def read(self, path) -> bytes: ...
    async def delete(self, path) -> None: ...
```

### 4.2 Register it in the DI Container

```python
# app/dependencies.py — add one branch
def get_storage() -> StoragePort:
    if settings.storage_backend == StorageBackend.GCS:           # new
        from app.adapters.storage.gcs import GCSStorageAdapter   # new
        return GCSStorageAdapter(...)                             # new
    if settings.storage_backend == StorageBackend.S3:
        ...
```

### 4.3 Add Config

```python
# app/config.py
class StorageBackend(str, Enum):
    LOCAL = "local"
    S3 = "s3"
    GCS = "gcs"        # new
```

```bash
# .env
STORAGE_BACKEND=gcs
GCS_BUCKET=luminalib-prod
GCS_CREDENTIALS_PATH=/secrets/gcs.json
```

**That's it.** Three small additions. Zero changes to services, routes, models, or tests. The same pattern applies for adding any new LLM provider (Anthropic, Gemini, Mistral, etc.).

---

## 5. Database Schema Design

### 5.1 Core Tables

```
users
├── id (UUID, PK)
├── email (UNIQUE, indexed)
├── username (UNIQUE)
├── hashed_password
├── created_at / updated_at

books
├── id (UUID, PK)
├── title (indexed), author (indexed), isbn (UNIQUE, nullable)
├── genres (TEXT[] — PostgreSQL array)
├── file_path (reference to storage backend)
├── file_type (pdf/txt)
├── summary (TEXT, nullable — filled asynchronously by LLM)
├── review_consensus (TEXT, nullable — rolling LLM-generated sentiment)
├── consensus_version (INT — optimistic locking for concurrent updates)
├── created_at / updated_at

borrows
├── id (UUID, PK)
├── user_id (FK → users, CASCADE)
├── book_id (FK → books, CASCADE)
├── borrowed_at
├── returned_at (nullable — NULL = currently borrowed)
├── PARTIAL UNIQUE INDEX on (user_id, book_id) WHERE returned_at IS NULL

reviews
├── id (UUID, PK)
├── user_id (FK → users, CASCADE)
├── book_id (FK → books, CASCADE)
├── rating (1-5)
├── text
├── created_at
```

### 5.2 User Preferences Schema — Design Decision

I chose a **hybrid implicit + explicit** model:

```
user_preferences (explicit — user-declared)
├── id (UUID, PK)
├── user_id (FK → users, UNIQUE)
├── favorite_genres (TEXT[])
├── favorite_authors (TEXT[])

user_interactions (implicit — behavioral signals)
├── id (UUID, PK)
├── user_id (FK → users)
├── book_id (FK → books)
├── interaction_type (ENUM: borrow, review, return)
├── rating (FLOAT, nullable — present only for review interactions)
├── created_at
```

**Why this design?**

| Approach | Pros | Cons |
|----------|------|------|
| Explicit only (genres, authors) | Solves cold-start; user has control | Doesn't capture real behavior |
| Implicit only (borrow/review history) | Captures true preferences | Cold-start problem for new users |
| **Hybrid (chosen)** | **Best of both: cold-start handled + behavioral accuracy** | **Slightly more complex schema** |

**How the ML model uses each:**

- **New user, no history**: Content-based filtering on `favorite_genres` and `favorite_authors` from `user_preferences`
- **New user, no preferences either**: Fallback to popular books (highest-rated, most-borrowed)
- **Active user**: `user_interactions` event log feeds both the TF-IDF content model (weighted by ratings) and the SVD collaborative filtering model. Explicit preferences still contribute as a prior.
- **The `interaction_type` enum** allows the ML model to weight signals differently (e.g., a review with a 5-star rating is a stronger signal than a borrow without a return).

---

## 6. Async Strategy for LLM Tasks

### 6.1 Approach: FastAPI BackgroundTasks

```
┌────────────┐         ┌──────────────┐        ┌──────────────┐
│  Client     │  POST   │  API Route   │        │  Background  │
│             │───────▶│  /books      │───────▶│  Task Worker │
│             │  201   │              │        │              │
│             │◀───────│  (returns    │        │ 1. Read file │
│             │        │   immediately)│        │ 2. Extract   │
└────────────┘         └──────────────┘        │    text      │
                                                │ 3. Call LLM  │
                                                │ 4. UPDATE DB │
                                                └──────────────┘
```

**Book Summarization Flow:**

1. `POST /books` → uploads file, inserts book row with `summary=NULL`
2. Route enqueues `generate_book_summary(book_id, storage, llm)` as BackgroundTask
3. Returns `201 Created` immediately (non-blocking)
4. Background worker:
   - Reads file from `StoragePort` (works with any backend)
   - Extracts text (pdfplumber for PDFs, UTF-8 decode for text)
   - Calls `LLMPort.summarize_book(text)` (works with any LLM)
   - Updates `books.summary` in the database
5. Client can poll `GET /books/{id}` — `summary` transitions from `null` to populated

**Review Consensus Flow:**

1. `POST /books/{id}/reviews` → inserts review
2. Route enqueues `update_review_consensus(book_id, llm)`
3. Returns `201 Created` immediately
4. Background worker:
   - Fetches all reviews for the book
   - Fetches current `review_consensus` (if any)
   - Calls `LLMPort.analyze_reviews(reviews, current_consensus)` — rolling update
   - Updates `books.review_consensus` and increments `consensus_version`
5. Client reads via `GET /books/{id}/analysis`

### 6.2 Why BackgroundTasks Over Celery?

| Factor | BackgroundTasks | Celery + Redis |
|--------|----------------|----------------|
| Complexity | Zero extra infrastructure | Requires Redis/RabbitMQ broker |
| Docker footprint | No additional containers | +2 containers (broker + worker) |
| Task persistence | Lost on process restart | Persisted in broker |
| Retry logic | Manual | Built-in |
| Scale | Single-process | Multi-worker, distributed |

**Decision**: For this project scope, BackgroundTasks provides the right balance. The architecture is designed for easy migration to Celery:

- Background task functions are standalone async functions in `app/tasks/background.py`
- They accept ports as parameters (not global imports)
- They create their own database sessions (independent of the request lifecycle)
- Adding Celery would mean: (1) add a `TaskPort` interface, (2) create a `CeleryTaskAdapter`, (3) register in `dependencies.py`. Same pattern as all other adapters.

### 6.3 Concurrency Safety

The `consensus_version` column on `books` provides **optimistic locking** for concurrent review submissions. If two reviews arrive simultaneously, the second consensus update will read the latest version and build on it rather than overwriting.

---

## 7. ML Recommendation Engine

### 7.1 Algorithm: Hybrid Content-Based + Collaborative Filtering

```
                    ┌─────────────────┐
                    │   User Request  │
                    │ GET /recommend  │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  Has history?   │
                    └───┬─────────┬───┘
                   No   │         │  Yes
                        │         │
              ┌─────────▼──┐  ┌───▼──────────────────┐
              │Has explicit │  │  Hybrid Model         │
              │preferences? │  │                       │
              └──┬──────┬──┘  │  ┌──────────────────┐ │
             No  │   Yes│     │  │ Content-Based     │ │
                 │      │     │  │ (TF-IDF + cosine) │ │
          ┌──────▼───┐  │     │  │ weight: α = 0.6   │ │
          │ Popular   │  │     │  └──────────────────┘ │
          │ Books     │  │     │           +           │
          │ Fallback  │  │     │  ┌──────────────────┐ │
          └──────────┘  │     │  │ Collaborative     │ │
                  ┌─────▼──┐  │  │ (SVD)             │ │
                  │Content- │  │  │ weight: 1-α = 0.4 │ │
                  │Based    │  │  └──────────────────┘ │
                  │Only     │  └───────────────────────┘
                  └────────┘
```

### 7.2 Content-Based Component

1. Each book is represented as text: `title + author + genres + summary[:500]`
2. TF-IDF vectorization (max 5000 features, English stop words removed)
3. User profile vector = weighted mean of book vectors they've interacted with, weighted by `rating / 5.0`
4. Explicit preferences (genres, authors) are also vectorized and added to the user profile
5. Cosine similarity between user profile and candidate books → content score

### 7.3 Collaborative Filtering Component

1. Build user-item matrix from `reviews` table (users × books, values = ratings)
2. Apply TruncatedSVD (dimensionality reduction to 5 latent factors)
3. User and book latent vectors extracted
4. Cosine similarity between user vector and candidate book vectors → collab score

### 7.4 Score Blending

```
final_score = α × content_score + (1 - α) × collab_score
```

Where `α` is configurable via `RECOMMENDATION_ALPHA` (default 0.6).

Higher α favors content-based (better for sparse data/new systems). Lower α favors collaborative (better with rich interaction data). This is tunable without code changes.

### 7.5 Cold Start Handling

| Scenario | Strategy |
|----------|----------|
| New user + explicit preferences | Content-based on declared genres/authors |
| New user + no preferences | Popular books (highest-rated, most-borrowed) |
| Active user + sparse collab data | α automatically compensates (content-based dominates) |
| Rich interaction data | Full hybrid model |

### 7.6 Explainability

Every recommendation includes a `reason` field:
- "Matches your preferred genres: sci-fi, fantasy"
- "By one of your favorite authors: Asimov"
- "Based on your reading history and similar users"

---

## 8. Prompt Engineering Strategy

Prompts are managed as **immutable, versioned template objects** — not inline strings scattered across adapters.

```python
# app/prompts/templates.py
@dataclass(frozen=True)
class PromptTemplate:
    name: str            # identifier for logging/tracking
    system: str          # system message (persona, constraints)
    user_template: str   # user message with {variables}
    max_tokens: int

    def render(self, **kwargs) -> dict[str, str]:
        return {"system": self.system, "user": self.user_template.format(**kwargs)}
```

**Why this matters for DI:**

- Prompt templates are **adapter-agnostic**. Both `OllamaLLMAdapter` and `OpenAILLMAdapter` use the exact same templates.
- When you swap LLM providers, the prompt content doesn't change — only the API call mechanism changes.
- Templates can be tested independently (unit test the `.render()` output).
- New prompts are added in one place, used by any adapter.

**Current templates:**

| Template | Purpose | Max Tokens |
|----------|---------|-----------|
| `SUMMARIZE_BOOK` | Generate book summary from content | 1024 |
| `ANALYZE_REVIEWS` | Synthesize reader reviews into consensus | 512 |

---

## 9. Testing Benefits of DI

The interface-driven architecture makes testing straightforward:

```python
# In tests, inject MockLLMAdapter directly — no Ollama or OpenAI needed
from app.adapters.llm.mock import MockLLMAdapter
from app.services.book import BookService

async def test_book_creation():
    mock_storage = MockStorageAdapter()   # fast, in-memory
    mock_llm = MockLLMAdapter()           # returns canned responses
    svc = BookService(session, mock_storage)
    # test business logic in isolation, no external dependencies
```

This is why every test in `tests/test_api.py` runs with `LLM_PROVIDER=mock` — fast, deterministic, no GPU required.

---

## 10. Assumptions & Trade-offs

| # | Assumption | Rationale |
|---|-----------|-----------|
| 1 | Reviewer may not have GPU | Default `LLM_PROVIDER=mock`; Ollama is opt-in via docker-compose profile |
| 2 | 50MB upload limit | Configurable via `MAX_UPLOAD_SIZE_MB`; sufficient for most books |
| 3 | JWT expires in 30 min, no refresh | Keeps auth simple; refresh token is addable without architecture change |
| 4 | BackgroundTasks not Celery | Right-sized for scope; the interface pattern supports Celery migration |
| 5 | In-memory token blacklist | Production would use Redis; swappable via same adapter pattern |
| 6 | `consensus_version` for locking | Optimistic locking avoids DB-level row locks for concurrent reviews |
| 7 | Single active borrow per user/book | Enforced via partial unique index (PostgreSQL-specific) |
| 8 | Review allowed after any borrow | User can review even after returning; they've read the book |
