import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    audit,
    auth,
    contacts,
    dashboard,
    health,
    members,
    organisations,
    policies,
    public,
    retention,
)
from app.config import get_settings
from app.errors import install_error_handlers
from app.frontend import mount_frontend


async def _retention_loop() -> None:
    """Apply the retention rules at start-up and then once a day (US-035B)."""
    from app.db import SessionLocal
    from app.retention import run_retention

    def run_once() -> None:
        with SessionLocal() as db:
            run_retention(db)

    while True:
        try:
            await asyncio.to_thread(run_once)
        except Exception:
            logging.getLogger("policy_compass").exception("Retention clean-up failed")
        await asyncio.sleep(24 * 60 * 60)


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
        retention_task = None
        if settings.retention_schedule_enabled:
            retention_task = asyncio.create_task(_retention_loop())
        yield
        if retention_task:
            retention_task.cancel()

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
    app.include_router(contacts.router, prefix="/api")
    app.include_router(dashboard.router, prefix="/api")
    app.include_router(retention.router, prefix="/api")
    app.include_router(public.router, prefix="/api")
    if settings.frontend_dist:
        mount_frontend(app, settings.frontend_dist)
    return app


app = create_app()
