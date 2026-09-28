import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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

_logger = logging.getLogger("api.main")

# Cooldown between repeated Telegram alerts for the same (path, exception
# type) pair, keyed on first-seen time. Without this, an outage that makes
# every request to one endpoint fail (e.g. the LLM provider going down)
# would fire one Telegram message per request instead of one per outage.
#
# time.monotonic() counts from an arbitrary point - in practice, system boot,
# not process start. A dev machine's uptime is usually days, so `now` is
# always far past any cooldown window for a key seen for the first time. A
# freshly booted VM (a CI runner, or this app right after a pm2 restart) can
# have an uptime under _ALERT_COOLDOWN_SECONDS though, and a 0.0 default for
# an unseen key would make `now - 0.0` read as still "within cooldown",
# silently swallowing the very first alert - found live when this exact
# scenario made a from-scratch CI runner's tests fail while passing
# everywhere else. -inf guarantees a key seen for the first time always
# alerts, regardless of how small `now` happens to be.
_ALERT_COOLDOWN_SECONDS = 600
_last_alert_at: dict[str, float] = {}
_NEVER_ALERTED = float("-inf")


@app.exception_handler(Exception)
async def _handle_unexpected_error(request: Request, exc: Exception):
    """Catches any exception a route didn't handle itself (HTTPException has
    its own default handler and never reaches here) - previously these were
    only visible by tailing pm2 logs on the VPS after a user reported a
    problem. Alerts to the same Telegram chat the source-refresh and review
    queue notifications already use, so a production error surfaces without
    anyone having to go looking for it."""
    _logger.exception("Unhandled error on %s %s", request.method, request.url.path)

    key = f"{request.url.path}:{type(exc).__name__}"
    now = time.monotonic()
    if now - _last_alert_at.get(key, _NEVER_ALERTED) > _ALERT_COOLDOWN_SECONDS:
        _last_alert_at[key] = now
        try:
            from api.telegram_bot import send_message

            send_message(
                f"Unhandled error on {request.method} {request.url.path}\n"
                f"{type(exc).__name__}: {exc}"
            )
        except Exception:
            _logger.exception("Failed to send Telegram error alert")

    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health")
def health():
    return {"status": "ok"}
