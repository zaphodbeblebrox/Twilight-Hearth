from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Invite, LoginSession, User, now
from ..schemas import AdminUserOut, InviteCreatedOut, InviteIn, InviteOut
from ..security import admin_user, create_invite

router = APIRouter(prefix="/api/admin", tags=["admin"])

Admin = Annotated[User, Depends(admin_user)]
Db = Annotated[Session, Depends(get_db)]


@router.get("/invites")
def list_invites(_: Admin, db: Db) -> list[InviteOut]:
    return db.scalars(select(Invite).order_by(Invite.created_at.desc())).all()


@router.post("/invites", status_code=201)
def add_invite(body: InviteIn, user: Admin, db: Db) -> InviteCreatedOut:
    invite, url = create_invite(db, email=body.email, created_by=user)
    return InviteCreatedOut(**InviteOut.model_validate(invite).model_dump(), url=url)


@router.delete("/invites/{invite_id}", status_code=204)
def revoke_invite(invite_id: UUID, _: Admin, db: Db) -> None:
    invite = db.get(Invite, invite_id)
    if invite is None:
        raise HTTPException(404, "Invite not found")
    invite.revoked_at = now()
    db.commit()


@router.get("/users")
def list_users(_: Admin, db: Db) -> list[AdminUserOut]:
    return db.scalars(select(User).order_by(User.created_at)).all()


def _set_disabled(db: Session, admin: User, user_id: UUID, disabled: bool) -> None:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    if user.id == admin.id:
        raise HTTPException(400, "You cannot disable yourself")
    user.disabled_at = now() if disabled else None
    db.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
    db.commit()


@router.post("/users/{user_id}/disable", status_code=204)
def disable_user(user_id: UUID, admin: Admin, db: Db) -> None:
    _set_disabled(db, admin, user_id, True)


@router.post("/users/{user_id}/enable", status_code=204)
def enable_user(user_id: UUID, admin: Admin, db: Db) -> None:
    _set_disabled(db, admin, user_id, False)
