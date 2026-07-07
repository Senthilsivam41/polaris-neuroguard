from pydantic import BaseModel

class Settings(BaseModel):
    PROJECT_NAME: str = "Polaris Neuro Guard"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"

settings = Settings()
