import hashlib
import secrets
from datetime import timedelta

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import Invite, LoginSession, User, now


class LoginRefused(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_invite(
    db: Session, *, email: str | None = None, created_by: User | None = None, admin: bool = False
) -> tuple[Invite, str]:
    token = secrets.token_urlsafe(32)
    invite = Invite(
        token_hash=hash_token(token),
        email=email.strip().lower() if email else None,
        makes_admin=admin,
        created_by_id=created_by.id if created_by else None,
        expires_at=now() + timedelta(days=get_settings().invite_days),
    )
    db.add(invite)
    db.commit()
    # A fragment is never sent to servers, so the token stays out of access logs.
    return invite, f"{get_settings().public_url}/join#{token}"


def sign_in(
    db: Session,
    *,
    sub: str,
    email: str,
    email_verified: bool,
    name: str,
    invite_token: str | None,
) -> str:
    """Return a new session token, admitting new people only with a valid invite."""
    user = db.scalar(select(User).where(User.google_sub == sub))
    if user is None:
        if not invite_token:
            raise LoginRefused("invite_required")
        # Locked so that one invite cannot be used twice at the same moment.
        invite = db.scalar(
            select(Invite).where(Invite.token_hash == hash_token(invite_token)).with_for_update()
        )
        if invite is None or invite.used_by_id or invite.revoked_at or invite.expires_at <= now():
            raise LoginRefused("invite_invalid")
        if invite.email and not (email_verified and email.lower() == invite.email):
            raise LoginRefused("invite_email_mismatch")
        user = User(
            google_sub=sub,
            email=email,
            display_name=(name or email.split("@")[0])[:100],
            is_admin=invite.makes_admin,
        )
        db.add(user)
        db.flush()
        invite.used_by_id = user.id
    elif user.disabled_at:
        raise LoginRefused("account_disabled")
    else:
        user.email = email
    db.execute(delete(LoginSession).where(LoginSession.expires_at <= now()))
    token = secrets.token_urlsafe(32)
    db.add(
        LoginSession(
            token_hash=hash_token(token),
            user_id=user.id,
            expires_at=now() + timedelta(days=get_settings().session_days),
        )
    )
    db.commit()
    return token


def set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        settings.session_cookie,
        token,
        max_age=settings.session_days * 86400,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        path="/",
    )


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(get_settings().session_cookie)
    if token:
        session = db.get(LoginSession, hash_token(token))
        if session and session.expires_at > now() and not session.user.disabled_at:
            return session.user
    raise HTTPException(401, "Not signed in")


def admin_user(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, "Admins only")
    return user
