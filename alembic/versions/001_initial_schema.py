"""Initial schema.

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("username", sa.String(100), unique=True, nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    # Books
    op.create_table(
        "books",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(500), nullable=False, index=True),
        sa.Column("author", sa.String(300), nullable=False, index=True),
        sa.Column("isbn", sa.String(20), unique=True, nullable=True),
        sa.Column("genres", postgresql.ARRAY(sa.String), server_default="{}"),
        sa.Column("file_path", sa.String(1000), nullable=False),
        sa.Column("file_type", sa.String(10), nullable=False),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("review_consensus", sa.Text, nullable=True),
        sa.Column("consensus_version", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    # Borrows
    op.create_table(
        "borrows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "book_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("books.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("borrowed_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("returned_at", sa.DateTime, nullable=True),
    )
    # Partial unique index: one active borrow per user per book
    op.create_index(
        "ix_active_borrow",
        "borrows",
        ["user_id", "book_id"],
        unique=True,
        postgresql_where=sa.text("returned_at IS NULL"),
    )

    # Reviews
    op.create_table(
        "reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "book_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("books.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rating", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_reviews_book", "reviews", ["book_id"])

    # User Preferences (explicit)
    op.create_table(
        "user_preferences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            unique=True,
            nullable=False,
        ),
        sa.Column("favorite_genres", postgresql.ARRAY(sa.String), server_default="{}"),
        sa.Column("favorite_authors", postgresql.ARRAY(sa.String), server_default="{}"),
    )

    # User Interactions (implicit signals for ML)
    interaction_type = postgresql.ENUM(
        "borrow", "review", "return", name="interaction_type_enum", create_type=True
    )
    op.create_table(
        "user_interactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "book_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("books.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("interaction_type", interaction_type, nullable=False),
        sa.Column("rating", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_interactions_user", "user_interactions", ["user_id"])
    op.create_index("ix_interactions_book", "user_interactions", ["book_id"])


def downgrade() -> None:
    op.drop_table("user_interactions")
    op.execute("DROP TYPE IF EXISTS interaction_type_enum")
    op.drop_table("user_preferences")
    op.drop_table("reviews")
    op.drop_index("ix_active_borrow", table_name="borrows")
    op.drop_table("borrows")
    op.drop_table("books")
    op.drop_table("users")alembic/versions/001_initial_schema.py
