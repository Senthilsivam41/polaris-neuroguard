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
