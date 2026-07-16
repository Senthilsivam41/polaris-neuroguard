import logging
import json
import asyncio
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import (PROJECT_NAME, VERSION, API_V1_STR, ALLOWED_ORIGINS,
                             MAX_REQUEST_BYTES, RATE_LIMIT_PER_MINUTE, REQUEST_TIMEOUT_SECONDS)
from app.api.endpoints import router as api_router
from app.core.security import current_principal

# ponytail: custom JSONFormatter subclassing standard logging.Formatter for JSON logging
class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_record = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_record)

# Configure root logger to output logs in structured JSON format
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# Clear any default pre-existing handlers
for h in root_logger.handlers[:]:
    root_logger.removeHandler(h)

handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
root_logger.addHandler(handler)

logger = logging.getLogger("app")

app = FastAPI(
    title=PROJECT_NAME,
    version=VERSION,
)

# Configure CORS Middleware for Frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)

_request_windows: dict[str, deque[float]] = defaultdict(deque)

@app.middleware("http")
async def abuse_protection(request: Request, call_next):
    """Bound request size, per-client rate, and execution time without logging secrets."""
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_REQUEST_BYTES:
        return JSONResponse(status_code=413, content={"detail": {"error_code": "PAYLOAD_TOO_LARGE"}})
    client = request.client.host if request.client else "unknown"
    now = time.monotonic()
    window = _request_windows[client]
    while window and window[0] <= now - 60:
        window.popleft()
    if len(window) >= RATE_LIMIT_PER_MINUTE:
        return JSONResponse(status_code=429, content={"detail": {"error_code": "RATE_LIMITED"}}, headers={"Retry-After": "60"})
    window.append(now)
    try:
        return await asyncio.wait_for(call_next(request), timeout=REQUEST_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        logger.warning("Request timed out: %s", request.url.path)
        return JSONResponse(status_code=504, content={"detail": {"error_code": "REQUEST_TIMEOUT"}})

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception occurred: %s", str(exc))
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected internal server error occurred."},
    )

@app.get("/health")
def health_check():
    return {"status": "ok"}

app.include_router(api_router, prefix=API_V1_STR, dependencies=[Depends(current_principal)])
