"""The only place that decides what a user may see. Every read must come through here."""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import ColumnElement, and_, or_, select
from sqlalchemy.orm import Session

from .models import Image, Recipe, Revision, User


def visible_to(user: User) -> ColumnElement[bool]:
    return and_(
        Recipe.deleted_at.is_(None),
        or_(Recipe.visibility == "members", Recipe.owner_id == user.id),
    )


def get_visible_recipe(db: Session, user: User, recipe_id: UUID) -> Recipe:
    recipe = db.scalar(select(Recipe).where(Recipe.id == recipe_id, visible_to(user)))
    if recipe is None:
        # Same answer for hidden and missing, so ids reveal nothing.
        raise HTTPException(404, "Recipe not found")
    return recipe


def get_owned_recipe(db: Session, user: User, recipe_id: UUID) -> Recipe:
    """Load a recipe for changing, locked so that edits happen one at a time."""
    recipe = db.scalar(
        select(Recipe).where(Recipe.id == recipe_id, visible_to(user)).with_for_update()
    )
    if recipe is None:
        raise HTTPException(404, "Recipe not found")
    if recipe.owner_id != user.id:
        raise HTTPException(403, "Only the owner can change this recipe. Fork it instead.")
    return recipe


def can_view_image(db: Session, user: User, image_id: UUID) -> bool:
    """Images are visible to their uploader and through any visible recipe's history."""
    image = db.get(Image, image_id)
    if image is None:
        return False
    if image.owner_id == user.id:
        return True
    return (
        db.scalar(
            select(Revision.id)
            .join(Recipe, Recipe.id == Revision.recipe_id)
            .where(Revision.content["image_id"].astext == str(image_id), visible_to(user))
            .limit(1)
        )
        is not None
    )
