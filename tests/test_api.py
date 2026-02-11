"""Integration tests for LuminaLib API."""

import io
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

BASE = "http://test"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url=BASE) as c:
        yield c


@pytest.fixture
async def auth_client(client: AsyncClient):
    """Register a user and return a client with auth headers."""
    email = f"test_{uuid4().hex[:8]}@example.com"
    username = f"user_{uuid4().hex[:8]}"
    await client.post(
        "/auth/signup",
        json={"email": email, "username": username, "password": "securepass123"},
    )
    resp = await client.post(
        "/auth/login",
        json={"email": email, "password": "securepass123"},
    )
    token = resp.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client


# ── Auth Tests ─────────────────────────────────────


@pytest.mark.asyncio
async def test_signup(client: AsyncClient):
    resp = await client.post(
        "/auth/signup",
        json={
            "email": f"new_{uuid4().hex[:8]}@example.com",
            "username": f"new_{uuid4().hex[:8]}",
            "password": "strongpass123",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "id" in data
    assert "email" in data


@pytest.mark.asyncio
async def test_signup_duplicate_email(client: AsyncClient):
    email = f"dup_{uuid4().hex[:8]}@example.com"
    payload = {"email": email, "username": "user1", "password": "strongpass123"}
    await client.post("/auth/signup", json=payload)
    payload["username"] = "user2"
    resp = await client.post("/auth/signup", json=payload)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    email = f"login_{uuid4().hex[:8]}@example.com"
    await client.post(
        "/auth/signup",
        json={"email": email, "username": f"u_{uuid4().hex[:6]}", "password": "pass12345"},
    )
    resp = await client.post(
        "/auth/login",
        json={"email": email, "password": "pass12345"},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_login_invalid_credentials(client: AsyncClient):
    resp = await client.post(
        "/auth/login",
        json={"email": "nonexistent@example.com", "password": "wrong"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_profile(auth_client: AsyncClient):
    resp = await auth_client.get("/auth/profile")
    assert resp.status_code == 200
    assert "email" in resp.json()


@pytest.mark.asyncio
async def test_signout(auth_client: AsyncClient):
    resp = await auth_client.post("/auth/signout")
    assert resp.status_code == 204
    # Token should now be invalid
    resp2 = await auth_client.get("/auth/profile")
    assert resp2.status_code == 401


# ── Books Tests ────────────────────────────────────


@pytest.mark.asyncio
async def test_unauthenticated_access(client: AsyncClient):
    resp = await client.get("/books")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_and_list_books(auth_client: AsyncClient):
    # Upload a book (multipart)
    file_content = b"This is a test book content for LuminaLib testing."
    resp = await auth_client.post(
        "/books",
        data={"title": "Test Book", "author": "Test Author", "genres": "fiction,sci-fi"},
        files={"file": ("test.txt", io.BytesIO(file_content), "text/plain")},
    )
    assert resp.status_code == 201
    book = resp.json()
    assert book["title"] == "Test Book"
    assert book["file_type"] == "txt"
    assert book["summary"] is None  # async, not ready yet

    # List books
    resp = await auth_client.get("/books?page=1&size=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert len(data["items"]) >= 1


@pytest.mark.asyncio
async def test_update_book(auth_client: AsyncClient):
    # Create
    resp = await auth_client.post(
        "/books",
        data={"title": "Old Title", "author": "Old Author"},
        files={"file": ("book.txt", io.BytesIO(b"content"), "text/plain")},
    )
    book_id = resp.json()["id"]

    # Update
    resp = await auth_client.put(
        f"/books/{book_id}",
        json={"title": "New Title", "author": "New Author"},
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "New Title"


@pytest.mark.asyncio
async def test_delete_book(auth_client: AsyncClient):
    resp = await auth_client.post(
        "/books",
        data={"title": "To Delete", "author": "Author"},
        files={"file": ("del.txt", io.BytesIO(b"delete me"), "text/plain")},
    )
    book_id = resp.json()["id"]

    resp = await auth_client.delete(f"/books/{book_id}")
    assert resp.status_code == 204

    resp = await auth_client.get(f"/books/{book_id}")
    assert resp.status_code == 404


# ── Borrow / Return Tests ─────────────────────────


@pytest.mark.asyncio
async def test_borrow_and_return(auth_client: AsyncClient):
    # Create book
    resp = await auth_client.post(
        "/books",
        data={"title": "Borrowable", "author": "Author"},
        files={"file": ("borrow.txt", io.BytesIO(b"content"), "text/plain")},
    )
    book_id = resp.json()["id"]

    # Borrow
    resp = await auth_client.post(f"/books/{book_id}/borrow")
    assert resp.status_code == 201
    assert resp.json()["returned_at"] is None

    # Double borrow should fail
    resp = await auth_client.post(f"/books/{book_id}/borrow")
    assert resp.status_code == 409

    # Return
    resp = await auth_client.post(f"/books/{book_id}/return")
    assert resp.status_code == 200
    assert resp.json()["returned_at"] is not None


# ── Review Tests ───────────────────────────────────


@pytest.mark.asyncio
async def test_review_requires_borrow(auth_client: AsyncClient):
    resp = await auth_client.post(
        "/books",
        data={"title": "No Borrow", "author": "Author"},
        files={"file": ("noborrow.txt", io.BytesIO(b"content"), "text/plain")},
    )
    book_id = resp.json()["id"]

    # Try to review without borrowing → 403
    resp = await auth_client.post(
        f"/books/{book_id}/reviews",
        json={"rating": 4, "text": "Great book, really enjoyed it!"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_review_after_borrow(auth_client: AsyncClient):
    resp = await auth_client.post(
        "/books",
        data={"title": "Reviewable", "author": "Author"},
        files={"file": ("review.txt", io.BytesIO(b"content"), "text/plain")},
    )
    book_id = resp.json()["id"]

    # Borrow first
    await auth_client.post(f"/books/{book_id}/borrow")

    # Now review
    resp = await auth_client.post(
        f"/books/{book_id}/reviews",
        json={"rating": 5, "text": "Absolutely fantastic read, highly recommend!"},
    )
    assert resp.status_code == 201
    assert resp.json()["rating"] == 5


# ── Intelligence Tests ─────────────────────────────


@pytest.mark.asyncio
async def test_analysis_endpoint(auth_client: AsyncClient):
    resp = await auth_client.post(
        "/books",
        data={"title": "Analyzable", "author": "Author"},
        files={"file": ("analyze.txt", io.BytesIO(b"content"), "text/plain")},
    )
    book_id = resp.json()["id"]

    resp = await auth_client.get(f"/books/{book_id}/analysis")
    assert resp.status_code == 200
    data = resp.json()
    assert data["book_id"] == book_id
    assert data["total_reviews"] == 0


@pytest.mark.asyncio
async def test_recommendations_endpoint(auth_client: AsyncClient):
    resp = await auth_client.get("/recommendations")
    assert resp.status_code == 200
    assert "recommendations" in resp.json()


@pytest.mark.asyncio
async def test_preferences(auth_client: AsyncClient):
    resp = await auth_client.put(
        "/preferences",
        json={"favorite_genres": ["sci-fi", "fantasy"], "favorite_authors": ["Asimov"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "sci-fi" in data["favorite_genres"]
    assert "Asimov" in data["favorite_authors"]


# ── Health Check ───────────────────────────────────


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"
