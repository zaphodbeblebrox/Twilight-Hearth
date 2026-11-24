from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def now() -> datetime:
    return datetime.now(UTC)


def timestamp(**kwargs):
    return mapped_column(DateTime(timezone=True), **kwargs)


class User(Base):
    __tablename__ = "users"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    # Google's permanent id. Email is for display only and may change.
    google_sub: Mapped[str] = mapped_column(String(255), unique=True)
    email: Mapped[str] = mapped_column(String(320))
    display_name: Mapped[str] = mapped_column(String(100))
    is_admin: Mapped[bool] = mapped_column(default=False)
    disabled_at: Mapped[datetime | None] = timestamp()
    created_at: Mapped[datetime] = timestamp(default=now)


class Invite(Base):
    __tablename__ = "invites"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    email: Mapped[str | None] = mapped_column(String(320))
    makes_admin: Mapped[bool] = mapped_column(default=False)
    created_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    used_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = timestamp()
    revoked_at: Mapped[datetime | None] = timestamp()
    created_at: Mapped[datetime] = timestamp(default=now)


class LoginSession(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = timestamp()
    user: Mapped[User] = relationship()


class Image(Base):
    __tablename__ = "images"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = timestamp(default=now)


class Recipe(Base):
    """A recipe under one user's control.

    Its content lives in immutable revisions. title, description, tags, image_id,
    total_minutes and search_text are copies from the current revision for listing.
    """

    __tablename__ = "recipes"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    visibility: Mapped[str] = mapped_column(String(16), default="members")
    current_number: Mapped[int] = mapped_column(default=1)
    # The recipe this was copied from. The exact version is revision 1's parent_id.
    forked_from_id: Mapped[UUID | None] = mapped_column(ForeignKey("recipes.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(40)), default=list)
    image_id: Mapped[UUID | None] = mapped_column(ForeignKey("images.id"))
    total_minutes: Mapped[int | None]
    search_text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = timestamp(default=now)
    updated_at: Mapped[datetime] = timestamp(default=now)
    deleted_at: Mapped[datetime | None] = timestamp()
    owner: Mapped[User] = relationship()

    __table_args__ = (
        CheckConstraint("visibility in ('members', 'private')", name="recipe_visibility"),
        Index("ix_recipes_tags", "tags", postgresql_using="gin"),
        Index(
            "ix_recipes_search",
            text("to_tsvector('english', search_text)"),
            postgresql_using="gin",
        ),
    )


class Revision(Base):
    __tablename__ = "revisions"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    recipe_id: Mapped[UUID] = mapped_column(ForeignKey("recipes.id"))
    number: Mapped[int]
    # May belong to another recipe: that is what a fork is.
    parent_id: Mapped[UUID | None] = mapped_column(ForeignKey("revisions.id"))
    author_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    message: Mapped[str] = mapped_column(String(200), default="")
    content: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = timestamp(default=now)
    author: Mapped[User] = relationship()

    __table_args__ = (
        UniqueConstraint("recipe_id", "number"),
        Index("ix_revisions_image", text("(content ->> 'image_id')")),
    )


class Favorite(Base):
    __tablename__ = "favorites"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    recipe_id: Mapped[UUID] = mapped_column(ForeignKey("recipes.id"), primary_key=True)


class Rating(Base):
    __tablename__ = "ratings"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    recipe_id: Mapped[UUID] = mapped_column(ForeignKey("recipes.id"), primary_key=True)
    stars: Mapped[int]
    __table_args__ = (CheckConstraint("stars between 1 and 5", name="rating_stars"),)


class Comment(Base):
    __tablename__ = "comments"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    recipe_id: Mapped[UUID] = mapped_column(ForeignKey("recipes.id"), index=True)
    author_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = timestamp(default=now)
    author: Mapped[User] = relationship()
