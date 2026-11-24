"""Recipe operations shared by the API routes."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Favorite, Rating, Recipe, Revision, User, now
from .permissions import visible_to
from .schemas import RecipeContent, RecipeOut, RecipeSummary, SourceOut, UserOut


def get_revision(db: Session, recipe: Recipe, number: int) -> Revision | None:
    return db.scalar(
        select(Revision).where(Revision.recipe_id == recipe.id, Revision.number == number)
    )


def current_revision(db: Session, recipe: Recipe) -> Revision:
    return get_revision(db, recipe, recipe.current_number)


def apply_content(recipe: Recipe, content: RecipeContent) -> None:
    recipe.title = content.title
    recipe.description = content.description
    recipe.tags = content.tags
    recipe.image_id = content.image_id
    times = [t for t in (content.prep_minutes, content.cook_minutes) if t is not None]
    recipe.total_minutes = sum(times) if times else None
    recipe.search_text = "\n".join(
        [content.title, content.description, " ".join(content.tags), content.source_name]
        + [i.text for g in content.ingredient_groups for i in g.items]
    )
    recipe.updated_at = now()


def _add_revision(
    db: Session,
    recipe: Recipe,
    user: User,
    content: RecipeContent,
    message: str,
    parent: Revision | None,
) -> None:
    db.add(
        Revision(
            recipe_id=recipe.id,
            number=recipe.current_number,
            parent_id=parent.id if parent else None,
            author_id=user.id,
            message=message,
            content=content.model_dump(mode="json"),
        )
    )
    db.commit()


def create_recipe(
    db: Session,
    user: User,
    content: RecipeContent,
    *,
    visibility: str,
    message: str = "",
    forked_from: Recipe | None = None,
    parent: Revision | None = None,
) -> Recipe:
    recipe = Recipe(
        owner_id=user.id,
        visibility=visibility,
        current_number=1,
        forked_from_id=forked_from.id if forked_from else None,
    )
    apply_content(recipe, content)
    db.add(recipe)
    db.flush()
    _add_revision(db, recipe, user, content, message, parent)
    return recipe


def save_revision(
    db: Session, recipe: Recipe, user: User, content: RecipeContent, message: str
) -> None:
    parent = current_revision(db, recipe)
    recipe.current_number += 1
    apply_content(recipe, content)
    _add_revision(db, recipe, user, content, message, parent)


def sources(db: Session, user: User, recipe: Recipe) -> list[SourceOut]:
    """Credit every ancestor, hiding details of any the viewer may not see."""
    found: list[SourceOut] = []
    # A fork always points to an older recipe, so this ends.
    while recipe.forked_from_id:
        source = db.get(Recipe, recipe.forked_from_id)
        parent = db.get(Revision, get_revision(db, recipe, 1).parent_id)
        credit = SourceOut(available=False, owner=UserOut.model_validate(source.owner))
        if db.scalar(select(Recipe.id).where(Recipe.id == source.id, visible_to(user))):
            credit.available = True
            credit.recipe_id = source.id
            credit.title = source.title
            credit.number = parent.number
        found.append(credit)
        recipe = source
    return found


def summaries(db: Session, user: User, recipes: list[Recipe]) -> list[RecipeSummary]:
    ids = [r.id for r in recipes]
    ratings = {
        row.recipe_id: row
        for row in db.execute(
            select(
                Rating.recipe_id,
                func.avg(Rating.stars).label("rating"),
                func.count().label("total"),
            )
            .where(Rating.recipe_id.in_(ids))
            .group_by(Rating.recipe_id)
        )
    }
    favorites = set(
        db.scalars(
            select(Favorite.recipe_id).where(
                Favorite.user_id == user.id, Favorite.recipe_id.in_(ids)
            )
        )
    )
    result = []
    for recipe in recipes:
        item = RecipeSummary.model_validate(recipe)
        item.is_fork = recipe.forked_from_id is not None
        item.is_favorite = recipe.id in favorites
        if row := ratings.get(recipe.id):
            item.rating = round(float(row.rating), 1)
            item.rating_count = row.total
        result.append(item)
    return result


def detail(db: Session, user: User, recipe: Recipe) -> RecipeOut:
    mine = db.get(Rating, (user.id, recipe.id))
    return RecipeOut(
        **summaries(db, user, [recipe])[0].model_dump(),
        content=RecipeContent.model_validate(current_revision(db, recipe).content),
        current_number=recipe.current_number,
        created_at=recipe.created_at,
        sources=sources(db, user, recipe),
        fork_count=db.scalar(
            select(func.count())
            .select_from(Recipe)
            .where(Recipe.forked_from_id == recipe.id, visible_to(user))
        ),
        my_rating=mine.stars if mine else None,
        can_edit=recipe.owner_id == user.id,
    )
