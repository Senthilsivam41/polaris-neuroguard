import math
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any

@dataclass
class Vector2D:
    magnitude: float
    heading_degrees: float

    def to_cartesian(self) -> Tuple[float, float]:
        """Convert magnitude and heading (degrees from positive Y-axis) to (dx, dy)."""
        rad = math.radians(self.heading_degrees)
        dx = self.magnitude * math.sin(rad)
        dy = self.magnitude * math.cos(rad)
        return dx, dy

    @classmethod
    def from_cartesian(cls, dx: float, dy: float) -> "Vector2D":
        """Convert (dx, dy) components back to a Vector2D."""
        magnitude = math.sqrt(dx * dx + dy * dy)
        if magnitude < 1e-9:
            return cls(magnitude=0.0, heading_degrees=0.0)
        
        # atan2(dx, dy) matches the heading measured from the positive Y axis (North)
        heading_rad = math.atan2(dx, dy)
        heading_deg = math.degrees(heading_rad)
        # Normalize to [0, 360)
        heading_deg = (heading_deg + 360.0) % 360.0
        return cls(magnitude=magnitude, heading_degrees=heading_deg)


@dataclass
class EnvironmentStorm:
    storm_type: str
    name: str
    force_vector: Vector2D
    cost_friction_multiplier: float = 1.0


# Pre-configured dynamic macro-environmental storm events
PRESET_STORMS: Dict[str, EnvironmentStorm] = {
    "Israel-Iraq Conflict": EnvironmentStorm(
        storm_type="Geopolitical",
        name="Israel-Iraq Conflict",
        force_vector=Vector2D(magnitude=5.0, heading_degrees=180.0),
        cost_friction_multiplier=1.0
    ),
    "Category 4 Cyclone": EnvironmentStorm(
        storm_type="Meteorological",
        name="Category 4 Cyclone",
        force_vector=Vector2D(magnitude=12.0, heading_degrees=90.0),
        cost_friction_multiplier=1.0
    ),
    "Surging Petrol Prices": EnvironmentStorm(
        storm_type="Economic",
        name="Surging Petrol Prices",
        force_vector=Vector2D(magnitude=0.0, heading_degrees=0.0),
        cost_friction_multiplier=1.35
    )
}


@dataclass
class Iceberg:
    name: str
    x: float
    y: float
    radius: float = 100.0


# Default systemic constraint icebergs
DEFAULT_ICEBERGS: List[Iceberg] = [
    Iceberg(name="Budget Lockout", x=-50.0, y=300.0, radius=100.0),
    Iceberg(name="Compliance Deadlock", x=60.0, y=600.0, radius=100.0),
    Iceberg(name="Schedule Slippage", x=150.0, y=200.0, radius=100.0),
    Iceberg(name="Scope Creep", x=-200.0, y=100.0, radius=100.0)
]

# Predefined opposing constraint pairs for deadlock checking
DEFAULT_OPPOSING_PAIRS: List[Tuple[str, str]] = [
    ("RIGID_TIMELINE", "FREEZE_HEADCOUNT"),
    ("REDUCE_COST", "EXPAND_SCOPE"),
    ("STRICT_QUALITY", "ACCELERATE_DELIVERY")
]


class SimulationEngine:
    @staticmethod
    def calculate_resultant_vector(intent_v: Vector2D, storms: List[EnvironmentStorm]) -> Vector2D:
        """Sum all vectors (intent + storms) to find the resultant vector."""
        total_dx, total_dy = intent_v.to_cartesian()
        
        for storm in storms:
            dx, dy = storm.force_vector.to_cartesian()
            total_dx += dx
            total_dy += dy
            
        return Vector2D.from_cartesian(total_dx, total_dy)

    @staticmethod
    def check_logical_deadlocks(
        declared_constraints: List[str],
        custom_pairs: List[Tuple[str, str]] = None
    ) -> List[Tuple[str, str]]:
        """Check for active system deadlocks when opposing constraints are simultaneously declared."""
        active_deadlocks = []
        pairs_to_check = DEFAULT_OPPOSING_PAIRS + (custom_pairs or [])
        
        # Normalize constraints to set for constant-time lookup
        constraints_set = {c.upper() for c in declared_constraints}
        
        for p1, p2 in pairs_to_check:
            if p1.upper() in constraints_set and p2.upper() in constraints_set:
                active_deadlocks.append((p1, p2))
                
        return active_deadlocks

    @staticmethod
    def check_trajectory_collision(
        start_x: float,
        start_y: float,
        resultant_v: Vector2D,
        icebergs: List[Iceberg]
    ) -> List[Iceberg]:
        """Project trajectory 3 turns in the future and check for circle capsule intersection."""
        dx, dy = resultant_v.to_cartesian()
        
        # End coordinates after 3 turns
        end_x = start_x + 3.0 * dx
        end_y = start_y + 3.0 * dy
        
        seg_dx = end_x - start_x
        seg_dy = end_y - start_y
        seg_len_sq = seg_dx * seg_dx + seg_dy * seg_dy
        
        intersecting_icebergs = []
        
        for iceberg in icebergs:
            # Vector from start of segment to iceberg center
            to_center_x = iceberg.x - start_x
            to_center_y = iceberg.y - start_y
            
            if seg_len_sq < 1e-9:
                # Segment is effectively a point (no movement)
                dist_sq = to_center_x * to_center_x + to_center_y * to_center_y
            else:
                # Project center onto segment, clamped to [0, 1]
                t = (to_center_x * seg_dx + to_center_y * seg_dy) / seg_len_sq
                t = max(0.0, min(1.0, t))
                
                # Find closest point on segment
                closest_x = start_x + t * seg_dx
                closest_y = start_y + t * seg_dy
                
                # Distance from closest point to center
                diff_x = iceberg.x - closest_x
                diff_y = iceberg.y - closest_y
                dist_sq = diff_x * diff_x + diff_y * diff_y
                
            if dist_sq <= iceberg.radius * iceberg.radius:
                intersecting_icebergs.append(iceberg)
                
        return intersecting_icebergs

    @staticmethod
    def execute_turn(
        current_x: float,
        current_y: float,
        intent_v: Vector2D,
        active_storms: List[EnvironmentStorm],
        base_burn_rate: float,
        declared_constraints: List[str],
        custom_icebergs: List[Iceberg] = None,
        custom_opposing_pairs: List[Tuple[str, str]] = None
    ) -> Dict[str, Any]:
        """Execute a single simulation step resolving deadlocks and checking for collisions."""
        # 1. Check for deadlocks
        active_deadlocks = SimulationEngine.check_logical_deadlocks(
            declared_constraints, custom_opposing_pairs
        )
        
        # If deadlocked, intentional velocity drops to 0
        resolved_intent = intent_v
        if active_deadlocks:
            resolved_intent = Vector2D(magnitude=0.0, heading_degrees=intent_v.heading_degrees)
            
        # 2. Compute resultant vector
        resultant_v = SimulationEngine.calculate_resultant_vector(resolved_intent, active_storms)
        dx, dy = resultant_v.to_cartesian()
        
        # 3. Advance ship position
        new_x = current_x + dx
        new_y = current_y + dy
        
        # 4. Check for collision threats along the path (look-ahead)
        all_icebergs = DEFAULT_ICEBERGS + (custom_icebergs or [])
        collisions = SimulationEngine.check_trajectory_collision(
            current_x, current_y, resultant_v, all_icebergs
        )
        
        # 5. Calculate financial cost of this turn
        friction_mult = 1.0
        for storm in active_storms:
            friction_mult *= storm.cost_friction_multiplier
        actual_burn_rate = base_burn_rate * friction_mult
        
        # 6. Quantify absolute angular drift delta
        theta_a = intent_v.heading_degrees
        theta_g = resultant_v.heading_degrees
        angle_diff = abs(theta_g - theta_a) % 360.0
        angular_drift_delta = min(angle_diff, 360.0 - angle_diff)
        
        return {
            "new_position": {"x": new_x, "y": new_y},
            "resultant_vector": resultant_v,
            "actual_burn_rate": actual_burn_rate,
            "angular_drift_delta": angular_drift_delta,
            "deadlocks": active_deadlocks,
            "collision_threats": collisions
        }
