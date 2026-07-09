import logging
import json
from datetime import datetime, timezone
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.core.config import PROJECT_NAME, VERSION, API_V1_STR
from app.api.endpoints import router as api_router

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

app.include_router(api_router, prefix=API_V1_STR)
