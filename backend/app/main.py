import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import audit, auth, health, members, organisations, policies, public
from app.config import get_settings
from app.errors import install_error_handlers
from app.frontend import mount_frontend


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=logging.INFO)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if settings.resume_processing_on_startup:
            from app.db import SessionLocal
            from app.processing import get_runner, resume_unfinished

            resumed = resume_unfinished(SessionLocal, get_runner())
            if resumed:
                logging.getLogger("policy_compass").info(
                    "Resumed processing for %d upload(s)", resumed
                )
        yield

    app = FastAPI(title="Policy Compass API", version="0.1.0", lifespan=lifespan)
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
    app.include_router(policies.router, prefix="/api")
    app.include_router(public.router, prefix="/api")
    if settings.frontend_dist:
        mount_frontend(app, settings.frontend_dist)
    return app


app = create_app()
