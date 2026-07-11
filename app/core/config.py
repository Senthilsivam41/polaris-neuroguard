import os
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

# Timeout and Retry configuration
GEMINI_TIMEOUT: float = float(os.getenv("GEMINI_TIMEOUT", "30.0"))
A2A_TIMEOUT: float = float(os.getenv("A2A_TIMEOUT", "60.0"))
ADK_RETRY_ATTEMPTS: int = int(os.getenv("ADK_RETRY_ATTEMPTS", "3"))
ADK_RETRY_INITIAL_DELAY: float = float(os.getenv("ADK_RETRY_INITIAL_DELAY", "2.0"))
ADK_RETRY_MAX_DELAY: float = float(os.getenv("ADK_RETRY_MAX_DELAY", "10.0"))
ADK_RETRY_BACKOFF_FACTOR: float = float(os.getenv("ADK_RETRY_BACKOFF_FACTOR", "2.0"))

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
    
    # Require GEMINI_API_KEY unless explicitly in offline/mock mode
    is_offline = OFFLINE_MODE or MOCK_MODE
    if not is_offline and not GEMINI_API_KEY:
        raise ValueError(
            "GEMINI_API_KEY is not configured in the environment. "
            "To bypass this check and run the application in offline mock mode, "
            "please set OFFLINE_MODE=true or MOCK_MODE=true in your environment or .env file."
        )

# Run validation on startup import
validate_config()

