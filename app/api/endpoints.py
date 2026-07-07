import uuid
import threading
from enum import Enum
from typing import Dict, Any
from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter()

# 1. Enums and Pydantic Schemas
class RiskTolerance(str, Enum):
    CONSERVATIVE = "Conservative"
    BALANCED = "Balanced"
    AGGRESSIVE = "Aggressive"

class AnchorGoal(BaseModel):
    title: str = Field(..., description="The title of the strategic goal")
    target_timeline_months: int = Field(..., description="Target timeline in months", gt=0)
    budget_limit_usd: float = Field(..., description="Strategic budget limit in USD", gt=0)
    reliability_target_sla: float = Field(..., description="Target reliability SLA", ge=0.0, le=100.0)

class CTOProfile(BaseModel):
    user_id: str = Field(..., description="The unique ID of the user")
    role: str = Field(..., description="The role of the user")
    company_scale: str = Field(..., description="The scale of the company")
    industry: str = Field(..., description="The industry of the company")
    anchor_goal: AnchorGoal = Field(..., description="The registered anchor goal")
    risk_tolerance: RiskTolerance = Field(..., description="Risk tolerance setting")

# 2. In-Memory Session Store
sessions: Dict[str, Dict[str, Any]] = {}
sessions_lock = threading.Lock()

@router.get("/status")
def get_status():
    return {"status": "ready"}

@router.post("/simulation/register")
def register_simulation(profile: CTOProfile):
    sim_id = str(uuid.uuid4())
    
    with sessions_lock:
        sessions[sim_id] = {
            "profile": profile.model_dump(),
            "destination": {"x": 0.0, "y": 1000.0}
        }
        
    return {
        "simulation_id": sim_id,
        "quantum_mountain_coordinates": {"x": 0.0, "y": 1000.0},
        "cto_profile": profile
    }

