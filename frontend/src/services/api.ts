export interface AnchorGoal {
  title: string;
  target_timeline_months: number;
  budget_limit_usd: number;
  reliability_target_sla: number;
}

export interface UserProfile {
  user_id: string;
  role: string;
  company_scale: string;
  industry: string;
  anchor_goal: AnchorGoal;
  risk_tolerance: 'Conservative' | 'Balanced' | 'Aggressive';
}

// CTOProfile aliases UserProfile for backward compatibility
export type CTOProfile = UserProfile;

export interface Vector2D {
  magnitude: number;
  heading_degrees: number;
}

export interface ShipTelemetry {
  current_position: { x: number; y: number };
  intent_vector: Vector2D;
  resultant_vector: Vector2D;
  actual_burn_rate: number;
  angular_drift_delta: number;
}

export interface HITLInterceptionData {
  requires_intervention: boolean;
  reason: string;
  telemetry_snapshot: any;
}

export interface EvaluateDecisionResponse {
  simulation_id: string;
  telemetry: ShipTelemetry;
  drift_warning: boolean;
  deadlocks: [string, string][];
  collision_threats: string[];
  hitl_interception_data: HITLInterceptionData | null;
  status: string;
  active_constraints: string[];
}

export interface HistoryStepLog {
  turn_number: number;
  telemetry_snapshot: ShipTelemetry;
  active_storms: string[];
  applied_decision: {
    intent_vector: Vector2D;
    declared_constraints: string[];
  };
  fracture_events: {
    deadlocks: [string, string][];
    collision_threats: string[];
    active_constraints: string[];
  };
}

export interface SimulationHistoryResponse {
  simulation_id: string;
  total_turns_executed: number;
  history: HistoryStepLog[];
}

export interface EnvironmentStorm {
  storm_type: 'Geopolitical' | 'Meteorological' | 'Economic';
  name: string;
  magnitude: number;
  heading_degrees: number;
}

const BASE_URL = '/api/v1';

export async function registerSimulation(profile: UserProfile): Promise<{ 
  simulation_id: string; 
  quantum_mountain_coordinates: { x: number; y: number }; 
  user_profile: UserProfile;
}> {
  const response = await fetch(`${BASE_URL}/simulation/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(profile),
  });
  if (!response.ok) throw new Error('Failed to register simulation session');
  return response.json();
}

export async function evaluateDecision(payload: {
  simulation_id: string;
  intent_vector: Vector2D;
  declared_constraints: string[];
  active_storms: string[];
  custom_icebergs?: any[];
  custom_opposing_pairs?: [string, string][];
}): Promise<EvaluateDecisionResponse> {
  const response = await fetch(`${BASE_URL}/simulation/evaluate-decision`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error('Failed to evaluate turn decision');
  return response.json();
}

export async function injectStorm(simulationId: string, storm: EnvironmentStorm): Promise<any> {
  const response = await fetch(`${BASE_URL}/simulation/${simulationId}/inject-storm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(storm),
  });
  if (!response.ok) throw new Error('Failed to inject custom storm');
  return response.json();
}

export async function getHistory(simulationId: string): Promise<SimulationHistoryResponse> {
  const response = await fetch(`${BASE_URL}/simulation/${simulationId}/history`);
  if (!response.ok) throw new Error('Failed to fetch path history logs');
  return response.json();
}
