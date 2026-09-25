import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes_admin import router as admin_router
from api.routes_auth import router as auth_router
from api.routes_chat import router as chat_router
from api.telegram_bot import start_background_polling
from config import settings
from db.models import init_db
from ingestion.chunker import scan_and_ingest_documents_folder

# Without this, INFO-level logs (e.g. graph/build_graph.py's per-node latency
# logging) are silently dropped - the root logger's default level is WARNING
# and nothing else in the app configures it.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scan_and_ingest_documents_folder()
    start_background_polling()
    yield


app = FastAPI(title="AEDS RAG", lifespan=lifespan)

# Any Vite dev port on localhost. Kept only for development: hardcoding it was
# fine while the only user was whoever ran the server, but a deployment serving
# real users needs its own origin allowed (see settings.cors_allow_origins).
_LOCAL_DEV_ORIGIN_REGEX = r"http://localhost:\d+"

_allowed_origins = [o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    # Localhost stays open in development only. In production the deployed
    # origin must be named explicitly via CORS_ALLOW_ORIGINS - leaving the
    # regex on would let any page served from a developer's machine call a
    # production API with the user's credentials attached.
    allow_origin_regex=None if settings.environment == "production" else _LOCAL_DEV_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(admin_router)


@app.get("/health")
def health():
    return {"status": "ok"}
