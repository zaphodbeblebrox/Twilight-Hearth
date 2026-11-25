from datetime import datetime
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from . import ingredients

ItemId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9-]{1,40}$")]
Line = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Paragraph = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]
Email = Annotated[str, StringConstraints(pattern=r"^[^@\s]+@[^@\s]+$", max_length=320)]
Visibility = Literal["members", "private"]


def strip_nul(value):
    """Postgres text and JSONB cannot hold NUL."""
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, list):
        return [strip_nul(v) for v in value]
    if isinstance(value, dict):
        return {k: strip_nul(v) for k, v in value.items()}
    return value


class Clean(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def no_nul(cls, data):
        return strip_nul(data)


class Ingredient(Clean):
    id: ItemId
    text: Line
    # Always recomputed from text by the server.
    quantity: str | None = None
    quantity_max: str | None = None
    unit: str | None = None
    food: str = ""

    @model_validator(mode="after")
    def parse_text(self):
        for key, value in ingredients.parse(self.text).items():
            setattr(self, key, value)
        return self


class IngredientGroup(Clean):
    id: ItemId
    name: str = Field("", max_length=100)
    items: list[Ingredient] = Field(default_factory=list, max_length=200)


class Step(Clean):
    id: ItemId
    text: Paragraph


class RecipeContent(Clean):
    schema_version: Literal[1] = 1
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    description: str = Field("", max_length=5000)
    servings: float | None = Field(None, gt=0, le=10000)
    yield_note: str = Field("", max_length=100)
    prep_minutes: int | None = Field(None, ge=0, le=100000)
    cook_minutes: int | None = Field(None, ge=0, le=100000)
    tags: list[str] = Field(default_factory=list, max_length=20)
    image_id: UUID | None = None
    # Where the recipe came from outside this site: a person, book or web page.
    source_name: str = Field("", max_length=200)
    source_url: str = Field("", max_length=2000)
    ingredient_groups: list[IngredientGroup] = Field(default_factory=list, max_length=30)
    steps: list[Step] = Field(default_factory=list, max_length=200)
    notes: str = Field("", max_length=10000)

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, tags: list[str]) -> list[str]:
        cleaned = [" ".join(t.lower().split())[:40] for t in tags]
        return list(dict.fromkeys(t for t in cleaned if t))

    @field_validator("source_url")
    @classmethod
    def web_links_only(cls, url: str) -> str:
        url = url.strip()
        if url:
            parts = urlsplit(url)
            if parts.scheme not in ("http", "https") or not parts.netloc:
                raise ValueError("must be an http or https address")
        return url

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [g.id for g in self.ingredient_groups]
        ids += [i.id for g in self.ingredient_groups for i in g.items]
        ids += [s.id for s in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("item ids must be unique")
        return self


class Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserOut(Out):
    id: UUID
    display_name: str


class MeOut(UserOut):
    email: str
    is_admin: bool


class AdminUserOut(MeOut):
    disabled_at: datetime | None
    created_at: datetime


class AuthConfigOut(BaseModel):
    google: bool
    dev_login: bool


class DevLoginIn(Clean):
    email: Email
    name: str = Field(min_length=1, max_length=100)


class TokenIn(BaseModel):
    token: str = Field(min_length=1, max_length=200)


class InviteIn(Clean):
    email: Email | None = None


class InviteOut(Out):
    id: UUID
    email: str | None
    expires_at: datetime
    revoked_at: datetime | None
    used_by_id: UUID | None
    created_at: datetime


class InviteCreatedOut(InviteOut):
    url: str


class ImageOut(Out):
    id: UUID


class ImportUrlIn(Clean):
    url: str = Field(min_length=1, max_length=2000)


class ImportOut(BaseModel):
    """A draft for the member to check. Nothing is saved as a recipe."""

    content: RecipeContent
    notice: str = ""


class RecipeCreateIn(Clean):
    content: RecipeContent
    visibility: Visibility = "members"
    message: str = Field("", max_length=200)


class RecipeUpdateIn(Clean):
    content: RecipeContent
    base_number: int
    message: str = Field("", max_length=200)


class RestoreIn(BaseModel):
    number: int
    base_number: int


class VisibilityIn(BaseModel):
    visibility: Visibility


class RatingIn(BaseModel):
    stars: int = Field(ge=1, le=5)


class CommentIn(Clean):
    body: Paragraph


class CommentOut(Out):
    id: UUID
    author: UserOut
    body: str
    created_at: datetime


class RecipeSummary(Out):
    id: UUID
    title: str
    description: str
    tags: list[str]
    image_id: UUID | None
    total_minutes: int | None
    visibility: Visibility
    owner: UserOut
    updated_at: datetime
    is_fork: bool = False
    rating: float | None = None
    rating_count: int = 0
    is_favorite: bool = False


class RecipePage(BaseModel):
    items: list[RecipeSummary]
    total: int


class SourceOut(BaseModel):
    """Credit for a recipe in this one's ancestry.

    recipe_id, title and number are withheld when the viewer may not see that recipe.
    """

    available: bool
    owner: UserOut
    recipe_id: UUID | None = None
    title: str | None = None
    number: int | None = None


class RecipeOut(RecipeSummary):
    content: RecipeContent
    current_number: int
    created_at: datetime
    # Nearest first: the recipe this was forked from, then what that was forked from...
    sources: list[SourceOut]
    fork_count: int
    my_rating: int | None
    can_edit: bool


class RevisionSummary(Out):
    number: int
    message: str
    author: UserOut
    created_at: datetime


class RevisionOut(RevisionSummary):
    content: RecipeContent


class TagOut(BaseModel):
    tag: str
    count: int
