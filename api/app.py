from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.bootstrap import ensure_project_root

ensure_project_root()

from api.routers import auth, chat, contacts, exports, health, jobs, meetings, metadata, privacy, realtime, stats, todos


def create_app() -> FastAPI:
    app = FastAPI(
        title="Meeting Agent API",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(meetings.router)
    app.include_router(exports.router)
    app.include_router(chat.router)
    app.include_router(jobs.router)
    app.include_router(metadata.router)
    app.include_router(privacy.router)
    app.include_router(realtime.router)
    app.include_router(stats.router)
    app.include_router(todos.router)
    app.include_router(contacts.router)
    return app


app = create_app()
