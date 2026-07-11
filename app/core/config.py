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

def validate_config():
    if BASE_BURN_RATE < 0.0:
        raise ValueError("BASE_BURN_RATE must be non-negative.")
    if not (0 < PORT <= 65535):
        raise ValueError("PORT must be a valid port number (1-65535).")
    
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

