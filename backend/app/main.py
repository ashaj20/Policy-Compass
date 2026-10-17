import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import audit, auth, health, members, organisations, public
from app.config import get_settings
from app.errors import install_error_handlers
from app.frontend import mount_frontend


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=logging.INFO)

    app = FastAPI(title="Policy Compass API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_error_handlers(app)
    app.include_router(health.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    app.include_router(organisations.router, prefix="/api")
    app.include_router(members.router, prefix="/api")
    app.include_router(audit.router, prefix="/api")
    app.include_router(public.router, prefix="/api")
    if settings.frontend_dist:
        mount_frontend(app, settings.frontend_dist)
    return app


app = create_app()
