from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import func, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .. import recipes as service
from ..db import get_db
from ..models import Comment, Favorite, Rating, Recipe, Revision, User, now
from ..permissions import can_view_image, get_owned_recipe, get_visible_recipe, visible_to
from ..schemas import (
    CommentIn,
    CommentOut,
    RatingIn,
    RecipeContent,
    RecipeCreateIn,
    RecipeOut,
    RecipePage,
    RecipeSummary,
    RecipeUpdateIn,
    RestoreIn,
    RevisionOut,
    RevisionSummary,
    TagOut,
    UserOut,
    VisibilityIn,
    strip_nul,
)
from ..security import current_user

router = APIRouter(prefix="/api", tags=["recipes"])

Me = Annotated[User, Depends(current_user)]
Db = Annotated[Session, Depends(get_db)]


def check_image(db: Session, user: User, content: RecipeContent) -> None:
    # Without this, naming someone's private image in a recipe would expose it.
    if content.image_id and not can_view_image(db, user, content.image_id):
        raise HTTPException(422, "Unknown image")


def check_base(recipe: Recipe, base_number: int) -> None:
    if recipe.current_number != base_number:
        raise HTTPException(409, "This recipe changed since you started editing")


@router.get("/recipes")
def list_recipes(
    user: Me,
    db: Db,
    q: str = Query("", max_length=200),
    tag: str = Query("", max_length=40),
    owner: UUID | None = None,
    favorites: bool = False,
    sort: Literal["recent", "rating", "title", "quick"] = "recent",
    limit: int = Query(24, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100_000),
) -> RecipePage:
    where = [visible_to(user)]
    if term := strip_nul(q).strip():
        vector = func.to_tsvector(text("'english'"), Recipe.search_text)
        where.append(
            or_(
                vector.bool_op("@@")(func.websearch_to_tsquery(text("'english'"), term)),
                Recipe.title.icontains(term, autoescape=True),
            )
        )
    if tag:
        where.append(Recipe.tags.contains([strip_nul(tag).lower()]))
    if owner:
        where.append(Recipe.owner_id == owner)
    if favorites:
        where.append(Recipe.id.in_(select(Favorite.recipe_id).where(Favorite.user_id == user.id)))
    average = select(func.avg(Rating.stars)).where(Rating.recipe_id == Recipe.id).scalar_subquery()
    order = {
        "recent": Recipe.updated_at.desc(),
        "rating": average.desc().nulls_last(),
        "title": func.lower(Recipe.title),
        "quick": Recipe.total_minutes.asc().nulls_last(),
    }[sort]
    rows = db.scalars(
        select(Recipe).where(*where).order_by(order, Recipe.id).limit(limit).offset(offset)
    ).all()
    total = db.scalar(select(func.count()).select_from(Recipe).where(*where))
    return RecipePage(items=service.summaries(db, user, rows), total=total)


@router.get("/tags")
def list_tags(user: Me, db: Db) -> list[TagOut]:
    tags = select(func.unnest(Recipe.tags).label("tag")).where(visible_to(user)).subquery()
    total = func.count().label("total")
    rows = db.execute(
        select(tags.c.tag, total).group_by(tags.c.tag).order_by(total.desc(), tags.c.tag).limit(50)
    )
    return [TagOut(tag=row.tag, count=row.total) for row in rows]


@router.get("/users/{user_id}")
def get_user(user_id: UUID, _: Me, db: Db) -> UserOut:
    found = db.get(User, user_id)
    if found is None:
        raise HTTPException(404, "User not found")
    return UserOut.model_validate(found)


@router.post("/recipes", status_code=201)
def create(body: RecipeCreateIn, user: Me, db: Db) -> RecipeOut:
    check_image(db, user, body.content)
    recipe = service.create_recipe(
        db, user, body.content, visibility=body.visibility, message=body.message
    )
    return service.detail(db, user, recipe)


@router.get("/recipes/{recipe_id}")
def get_one(recipe_id: UUID, user: Me, db: Db) -> RecipeOut:
    return service.detail(db, user, get_visible_recipe(db, user, recipe_id))


@router.put("/recipes/{recipe_id}")
def update(recipe_id: UUID, body: RecipeUpdateIn, user: Me, db: Db) -> RecipeOut:
    recipe = get_owned_recipe(db, user, recipe_id)
    check_base(recipe, body.base_number)
    check_image(db, user, body.content)
    service.save_revision(db, recipe, user, body.content, body.message)
    return service.detail(db, user, recipe)


@router.delete("/recipes/{recipe_id}", status_code=204)
def remove(recipe_id: UUID, user: Me, db: Db) -> None:
    get_owned_recipe(db, user, recipe_id).deleted_at = now()
    db.commit()


@router.put("/recipes/{recipe_id}/visibility")
def set_visibility(recipe_id: UUID, body: VisibilityIn, user: Me, db: Db) -> RecipeOut:
    recipe = get_owned_recipe(db, user, recipe_id)
    recipe.visibility = body.visibility
    db.commit()
    return service.detail(db, user, recipe)


@router.get("/recipes/{recipe_id}/revisions")
def list_revisions(recipe_id: UUID, user: Me, db: Db) -> list[RevisionSummary]:
    recipe = get_visible_recipe(db, user, recipe_id)
    return db.scalars(
        select(Revision).where(Revision.recipe_id == recipe.id).order_by(Revision.number.desc())
    ).all()


@router.get("/recipes/{recipe_id}/revisions/{number}")
def get_revision(
    recipe_id: UUID, number: Annotated[int, Path(ge=1, le=1_000_000)], user: Me, db: Db
) -> RevisionOut:
    revision = service.get_revision(db, get_visible_recipe(db, user, recipe_id), number)
    if revision is None:
        raise HTTPException(404, "Version not found")
    return RevisionOut.model_validate(revision)


@router.post("/recipes/{recipe_id}/restore")
def restore(recipe_id: UUID, body: RestoreIn, user: Me, db: Db) -> RecipeOut:
    recipe = get_owned_recipe(db, user, recipe_id)
    check_base(recipe, body.base_number)
    old = service.get_revision(db, recipe, body.number)
    if old is None:
        raise HTTPException(404, "Version not found")
    content = RecipeContent.model_validate(old.content)
    service.save_revision(db, recipe, user, content, f"Restored version {old.number}")
    return service.detail(db, user, recipe)


@router.post("/recipes/{recipe_id}/fork", status_code=201)
def fork(recipe_id: UUID, user: Me, db: Db) -> RecipeOut:
    """Copy a recipe into the user's control, keeping a link back to the exact version."""
    source = get_visible_recipe(db, user, recipe_id)
    revision = service.current_revision(db, source)
    copy = service.create_recipe(
        db,
        user,
        RecipeContent.model_validate(revision.content),
        visibility=source.visibility,
        message="Forked",
        forked_from=source,
        parent=revision,
    )
    return service.detail(db, user, copy)


@router.get("/recipes/{recipe_id}/forks")
def list_forks(recipe_id: UUID, user: Me, db: Db) -> list[RecipeSummary]:
    source = get_visible_recipe(db, user, recipe_id)
    rows = db.scalars(
        select(Recipe)
        .where(Recipe.forked_from_id == source.id, visible_to(user))
        .order_by(Recipe.created_at)
    ).all()
    return service.summaries(db, user, rows)


@router.put("/recipes/{recipe_id}/favorite", status_code=204)
def add_favorite(recipe_id: UUID, user: Me, db: Db) -> None:
    get_visible_recipe(db, user, recipe_id)
    db.execute(
        insert(Favorite).values(user_id=user.id, recipe_id=recipe_id).on_conflict_do_nothing()
    )
    db.commit()


@router.delete("/recipes/{recipe_id}/favorite", status_code=204)
def remove_favorite(recipe_id: UUID, user: Me, db: Db) -> None:
    if favorite := db.get(Favorite, (user.id, recipe_id)):
        db.delete(favorite)
        db.commit()


@router.put("/recipes/{recipe_id}/rating", status_code=204)
def rate(recipe_id: UUID, body: RatingIn, user: Me, db: Db) -> None:
    get_visible_recipe(db, user, recipe_id)
    db.execute(
        insert(Rating)
        .values(user_id=user.id, recipe_id=recipe_id, stars=body.stars)
        .on_conflict_do_update(index_elements=["user_id", "recipe_id"], set_={"stars": body.stars})
    )
    db.commit()


@router.get("/recipes/{recipe_id}/comments")
def list_comments(recipe_id: UUID, user: Me, db: Db) -> list[CommentOut]:
    recipe = get_visible_recipe(db, user, recipe_id)
    return db.scalars(
        select(Comment).where(Comment.recipe_id == recipe.id).order_by(Comment.created_at)
    ).all()


@router.post("/recipes/{recipe_id}/comments", status_code=201)
def add_comment(recipe_id: UUID, body: CommentIn, user: Me, db: Db) -> CommentOut:
    recipe = get_visible_recipe(db, user, recipe_id)
    comment = Comment(recipe_id=recipe.id, author_id=user.id, body=body.body)
    db.add(comment)
    db.commit()
    return CommentOut.model_validate(comment)


@router.delete("/recipes/{recipe_id}/comments/{comment_id}", status_code=204)
def remove_comment(recipe_id: UUID, comment_id: UUID, user: Me, db: Db) -> None:
    recipe = get_visible_recipe(db, user, recipe_id)
    comment = db.get(Comment, comment_id)
    if comment is None or comment.recipe_id != recipe.id:
        raise HTTPException(404, "Comment not found")
    if user.id not in (comment.author_id, recipe.owner_id) and not user.is_admin:
        raise HTTPException(403, "You cannot delete this comment")
    db.delete(comment)
    db.commit()
