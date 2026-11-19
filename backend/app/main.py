import logging
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .ai.llm_client import llm_status, start_llm
from .core.config import settings
from .routers import (
    admin,
    appointments,
    business,
    chat,
    conversations,
    customers,
    dashboard,
    faqs,
    handoffs,
    leads,
    public_appointments,
)
from .utils.logger import log_debug_data

logger = logging.getLogger("ava")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.run_migrations_on_startup:
        from .db_migrate import run_migrations

        run_migrations()
    if settings.seed_on_startup:
        from .seed import run_seed

        run_seed()
    start_llm()  # loads the local model in a background thread (if LLM_PROVIDER=local)
    yield


app = FastAPI(title="Ava AI Receptionist API", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,  # auth uses Bearer tokens, not cookies
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

for module in (admin, chat, public_appointments, appointments, customers, leads, conversations, faqs, business,
               handoffs, dashboard):
    app.include_router(module.router)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    # Readable messages without echoing the submitted values back.
    errors = [{"field": ".".join(str(p) for p in e.get("loc", [])[1:]), "message": e.get("msg")}
              for e in exc.errors()]
    first = errors[0] if errors else {"field": "", "message": "Invalid request"}
    detail = f"{first['field']}: {first['message']}" if first["field"] else first["message"]
    return JSONResponse(status_code=422, content={"detail": detail, "errors": errors})


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Logs unexpected errors (without request bodies) and returns a generic 500."""
    log_debug_data("UNHANDLED ERROR", {
        "path": request.url.path,
        "method": request.method,
        "error_type": type(exc).__name__,
        "traceback": traceback.format_exc(),
    }, type="error")
    logger.error("Unhandled error on %s %s: %s", request.method, request.url.path, type(exc).__name__)
    return JSONResponse(status_code=500, content={"detail": "An internal server error occurred."})


@app.get("/api/health")
def health():
    return {"status": "ok", "llm": llm_status()["status"]}
