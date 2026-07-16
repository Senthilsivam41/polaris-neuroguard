import os
import json
from dotenv import load_dotenv

# Load environment variables from a .env file if it exists
load_dotenv()

# config parameters fetched dynamically from the environment
PROJECT_NAME: str = os.getenv("PROJECT_NAME", "Polaris Neuro Guard")
VERSION: str = os.getenv("VERSION", "1.0.0")
API_V1_STR: str = os.getenv("API_V1_STR", "/api/v1")

# Baseline cost burn-rate per turn (defaults to 100.0)
BASE_BURN_RATE: float = float(os.getenv("BASE_BURN_RATE", "100.0"))

# Default application port (defaults to 8000)
PORT: int = int(os.getenv("PORT", "8000"))

# Gemini API Key and Model configurations
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
OFFLINE_MODE: bool = os.getenv("OFFLINE_MODE", "false").lower() == "true"
MOCK_MODE: bool = os.getenv("MOCK_MODE", "false").lower() == "true"
IS_OFFLINE: bool = OFFLINE_MODE or MOCK_MODE

# Timeout and Retry configuration
GEMINI_TIMEOUT: float = float(os.getenv("GEMINI_TIMEOUT", "30.0"))
A2A_TIMEOUT: float = float(os.getenv("A2A_TIMEOUT", "60.0"))
ADK_RETRY_ATTEMPTS: int = int(os.getenv("ADK_RETRY_ATTEMPTS", "3"))
ADK_RETRY_INITIAL_DELAY: float = float(os.getenv("ADK_RETRY_INITIAL_DELAY", "2.0"))
ADK_RETRY_MAX_DELAY: float = float(os.getenv("ADK_RETRY_MAX_DELAY", "10.0"))
ADK_RETRY_BACKOFF_FACTOR: float = float(os.getenv("ADK_RETRY_BACKOFF_FACTOR", "2.0"))

# Phase 6 API hardening.  Production deployments must explicitly configure
# tokens; the development token is available only in offline/mock mode.
AUTH_REQUIRED: bool = os.getenv("AUTH_REQUIRED", "true").lower() == "true"
API_TOKENS_JSON: str = os.getenv("POLARIS_API_TOKENS", "{}")
ALLOWED_ORIGINS: list[str] = [origin.strip() for origin in os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
).split(",") if origin.strip()]
RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "99999" if IS_OFFLINE else "60"))
MAX_REQUEST_BYTES: int = int(os.getenv("MAX_REQUEST_BYTES", "65536"))
REQUEST_TIMEOUT_SECONDS: float = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))

# Phase 7 observability labels. Never use request IDs, actors, or prompts as metric labels.
DEPLOYMENT_ENV: str = os.getenv("DEPLOYMENT_ENV", "development")

try:
    API_TOKENS: dict[str, dict] = json.loads(API_TOKENS_JSON)
except json.JSONDecodeError as exc:
    raise ValueError("POLARIS_API_TOKENS must be a JSON object keyed by token.") from exc

if (OFFLINE_MODE or MOCK_MODE) and not API_TOKENS:
    API_TOKENS = {"dev-local-token": {"actor_id": "dev-user", "roles": ["operator", "reviewer", "override"]}}

def validate_config():
    if BASE_BURN_RATE < 0.0:
        raise ValueError("BASE_BURN_RATE must be non-negative.")
    if not (0 < PORT <= 65535):
        raise ValueError("PORT must be a valid port number (1-65535).")
    
    # Validate Timeouts and Retries
    if GEMINI_TIMEOUT <= 0.0:
        raise ValueError("GEMINI_TIMEOUT must be positive.")
    if A2A_TIMEOUT <= 0.0:
        raise ValueError("A2A_TIMEOUT must be positive.")
    if ADK_RETRY_ATTEMPTS < 0:
        raise ValueError("ADK_RETRY_ATTEMPTS must be non-negative.")
    if ADK_RETRY_INITIAL_DELAY < 0.0:
        raise ValueError("ADK_RETRY_INITIAL_DELAY must be non-negative.")
    if ADK_RETRY_MAX_DELAY < ADK_RETRY_INITIAL_DELAY:
        raise ValueError("ADK_RETRY_MAX_DELAY must be greater than or equal to ADK_RETRY_INITIAL_DELAY.")
    if ADK_RETRY_BACKOFF_FACTOR < 1.0:
        raise ValueError("ADK_RETRY_BACKOFF_FACTOR must be greater than or equal to 1.0.")
    if RATE_LIMIT_PER_MINUTE <= 0 or MAX_REQUEST_BYTES <= 0 or REQUEST_TIMEOUT_SECONDS <= 0:
        raise ValueError("Phase 6 rate, size, and timeout settings must be positive.")
    
    # Require GEMINI_API_KEY unless explicitly in offline/mock mode
    is_offline = OFFLINE_MODE or MOCK_MODE
    if not is_offline and not GEMINI_API_KEY:
        raise ValueError(
            "GEMINI_API_KEY is not configured in the environment. "
            "To bypass this check and run the application in offline mock mode, "
            "please set OFFLINE_MODE=true or MOCK_MODE=true in your environment or .env file."
        )
    if AUTH_REQUIRED and not API_TOKENS and not is_offline:
        raise ValueError("POLARIS_API_TOKENS must configure at least one API token when authentication is required.")

# Run validation on startup import
validate_config()

def get_redacted_api_key() -> str:
    """Mask the Gemini API key to avoid accidental leakage in logs."""
    if not GEMINI_API_KEY:
        return ""
    if len(GEMINI_API_KEY) <= 8:
        return "********"
    return f"{GEMINI_API_KEY[:4]}...{GEMINI_API_KEY[-4:]}"


from google.adk.workflow import RetryConfig

WORKFLOW_RETRY_CONFIG = RetryConfig(
    max_attempts=ADK_RETRY_ATTEMPTS,
    initial_delay=ADK_RETRY_INITIAL_DELAY,
    max_delay=ADK_RETRY_MAX_DELAY,
    backoff_factor=ADK_RETRY_BACKOFF_FACTOR,
)
