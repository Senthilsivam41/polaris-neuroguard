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

def validate_config():
    if BASE_BURN_RATE < 0.0:
        raise ValueError("BASE_BURN_RATE must be non-negative.")
    if not (0 < PORT <= 65535):
        raise ValueError("PORT must be a valid port number (1-65535).")
    # Log warning if API key is missing
    if not GEMINI_API_KEY:
        import sys
        print(
            "WARNING: GEMINI_API_KEY is not configured in the environment. "
            "Simulation will run in mock/offline mode.",
            file=sys.stderr
        )

# Run validation on startup import
validate_config()

