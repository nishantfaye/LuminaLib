"""SQLAlchemy ORM models."""

import uuid
from datetime import datetime

from sqlalchemy import (
    ARRAY,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    borrows = relationship("Borrow", back_populates="user", lazy="selectin")
    reviews = relationship("Review", back_populates="user", lazy="selectin")
    preferences = relationship("UserPreference", back_populates="user", uselist=False, lazy="selectin")
    interactions = relationship("UserInteraction", back_populates="user", lazy="selectin")


class Book(Base):
    __tablename__ = "books"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(500), nullable=False, index=True)
    author = Column(String(300), nullable=False, index=True)
    isbn = Column(String(20), unique=True, nullable=True)
    genres = Column(ARRAY(String), default=list)
    file_path = Column(String(1000), nullable=False)
    file_type = Column(String(10), nullable=False)
    summary = Column(Text, nullable=True)
    review_consensus = Column(Text, nullable=True)
    consensus_version = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    borrows = relationship("Borrow", back_populates="book", lazy="selectin")
    reviews = relationship("Review", back_populates="book", lazy="selectin")


class Borrow(Base):
    __tablename__ = "borrows"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    book_id = Column(UUID(as_uuid=True), ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    borrowed_at = Column(DateTime, default=datetime.utcnow)
    returned_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="borrows")
    book = relationship("Book", back_populates="borrows")


class Review(Base):
    __tablename__ = "reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    book_id = Column(UUID(as_uuid=True), ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    rating = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="reviews")
    book = relationship("Book", back_populates="reviews")


class UserPreference(Base):
    __tablename__ = "user_preferences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False)
    favorite_genres = Column(ARRAY(String), default=list)
    favorite_authors = Column(ARRAY(String), default=list)

    user = relationship("User", back_populates="preferences")


class UserInteraction(Base):
    __tablename__ = "user_interactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    book_id = Column(UUID(as_uuid=True), ForeignKey("books.id"), nullable=False)
    interaction_type = Column(
        Enum("borrow", "review", "return", name="interaction_type_enum"),
        nullable=False,
    )
    rating = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="interactions")
