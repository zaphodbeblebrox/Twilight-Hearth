from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from .config import get_settings
from .routers import admin, auth, images, recipes


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Twilight Hearth",
        docs_url=None if settings.is_production else "/api/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/api/openapi.json",
    )

    # Short-lived signed cookie that carries OAuth state and a pending invite.
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie="__Host-th_login" if settings.is_production else "th_login",
        max_age=15 * 60,
        same_site="lax",
        https_only=settings.is_production,
    )

    @app.middleware("http")
    async def require_same_origin(request: Request, call_next):
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            if request.headers.get("origin") != settings.public_url:
                return JSONResponse({"detail": "Cross-site request refused"}, 403)
        return await call_next(request)

    @app.get("/api/health", include_in_schema=False)
    def health():
        return {"status": "ok"}

    for module in (auth, admin, recipes, images):
        app.include_router(module.router)
    if not settings.is_production:
        app.post("/api/auth/dev-login", status_code=204, tags=["auth"])(auth.dev_login)
    return app


app = create_app()
