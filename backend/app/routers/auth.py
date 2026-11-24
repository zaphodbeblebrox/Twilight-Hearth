from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse
from sqlalchemy import delete
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import LoginSession, User
from ..schemas import AuthConfigOut, DevLoginIn, MeOut, TokenIn
from ..security import LoginRefused, current_user, hash_token, set_session_cookie, sign_in

router = APIRouter(prefix="/api/auth", tags=["auth"])


def google_client():
    settings = get_settings()
    if not settings.google_client_id:
        raise HTTPException(404, "Google login is not configured")
    return OAuth().register(
        "google",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile", "code_challenge_method": "S256"},
    )


@router.get("/config")
def auth_config() -> AuthConfigOut:
    settings = get_settings()
    return AuthConfigOut(
        google=bool(settings.google_client_id), dev_login=not settings.is_production
    )


@router.post("/invite", status_code=204)
def hold_invite(body: TokenIn, request: Request) -> None:
    """Remember the invite in the signed, HttpOnly login cookie while visiting Google."""
    request.session["invite"] = body.token


@router.get("/google/login", include_in_schema=False)
async def google_login(request: Request):
    callback = f"{get_settings().public_url}/api/auth/google/callback"
    return await google_client().authorize_redirect(request, callback, prompt="select_account")


@router.get("/google/callback", include_in_schema=False)
async def google_callback(request: Request, db: Session = Depends(get_db)):
    base = get_settings().public_url
    try:
        # Checks state, PKCE, and the ID token's signature, issuer, audience, expiry, nonce.
        token = await google_client().authorize_access_token(request)
    except OAuthError:
        return RedirectResponse(f"{base}/login?error=google_failed", 303)
    claims = token.get("userinfo")
    if not claims or not claims.get("sub") or not claims.get("email"):
        return RedirectResponse(f"{base}/login?error=google_failed", 303)
    try:
        session_token = await run_in_threadpool(
            sign_in,
            db,
            sub=claims["sub"],
            email=claims["email"],
            email_verified=claims.get("email_verified") is True,
            name=claims.get("name", ""),
            invite_token=request.session.get("invite"),
        )
    except LoginRefused as refused:
        return RedirectResponse(f"{base}/login?error={refused.code}", 303)
    request.session.clear()
    response = RedirectResponse(f"{base}/", 303)
    set_session_cookie(response, session_token)
    return response


# Registered by main.py outside production only.
def dev_login(
    body: DevLoginIn, request: Request, response: Response, db: Session = Depends(get_db)
) -> None:
    """Stand-in for Google that follows the same invite rules."""
    try:
        token = sign_in(
            db,
            sub=f"dev:{body.email.lower()}",
            email=body.email.lower(),
            email_verified=True,
            name=body.name,
            invite_token=request.session.get("invite"),
        )
    except LoginRefused as refused:
        raise HTTPException(403, refused.code) from None
    request.session.clear()
    set_session_cookie(response, token)


@router.get("/me")
def me(user: User = Depends(current_user)) -> MeOut:
    return MeOut.model_validate(user)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> None:
    settings = get_settings()
    if token := request.cookies.get(settings.session_cookie):
        db.execute(delete(LoginSession).where(LoginSession.token_hash == hash_token(token)))
        db.commit()
    response.delete_cookie(
        settings.session_cookie, path="/", secure=settings.is_production, httponly=True
    )
