from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.api.actions import router as actions_router
from app.api.auth import router as auth_router
from app.api.client import router as client_router
from app.api.dashboard import router as dashboard_router
from app.config import get_settings
from app.websocket.client import router as websocket_router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in settings.cors_dashboard_origins.split(",") if origin.strip()],
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization"],
    )
    app.add_middleware(SessionMiddleware, secret_key=settings.jwt_secret, same_site="lax", https_only=settings.environment == "production")
    app.include_router(auth_router)
    app.include_router(client_router)
    app.include_router(actions_router)
    app.include_router(dashboard_router)
    app.include_router(websocket_router)

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"ok": True}

    @app.get("/readyz")
    async def readyz() -> dict:
        return {"ready": True}

    return app


app = create_app()
