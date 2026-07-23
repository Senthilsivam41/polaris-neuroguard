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
  telemetry_snapshot: {
    deadlocks?: [string, string][];
    threats?: string[];
    [key: string]: unknown;
  };
  checkpoint_id?: string | null;
  checkpoint_version?: number | null;
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

export interface ResumeSimulationRequest {
  checkpoint_id: string;
  resume_request_id: string;
  actor_id: string;
  resolution_action: string;
  expected_checkpoint_version: number;
  intent_vector?: Vector2D;
  declared_constraints?: string[];
  approval_decision_id?: string;
  amendment_id?: string;
}

export interface ResumeSimulationResponse {
  simulation_id: string;
  checkpoint_id: string;
  resumed_invocation_id: string;
  resume_status: string;
  current_workflow_state: Record<string, unknown>;
  telemetry: ShipTelemetry;
  active_contract_version: number;
  remaining_interruption_details: Record<string, unknown> | null;
  correlation_id: string;
}

export interface ChangeRequestResponse {
  request_id: string;
  contract_id: string;
  active_contract_version: number;
  idempotency_result: string;
  request_acceptance_status: string;
  classification_status: string;
  trace_id: string;
}

export interface DriftEvaluationResult {
  request_id: string;
  recommended_action?: string;
  classification_status?: string;
  deterministic_findings?: Array<{ category: string; evidence?: string }>;
  semantic_score?: number;
  risk_profile?: string;
  [key: string]: unknown;
}

export interface ConfirmAmendmentResponse {
  request_id: string;
  contract_id: string;
  active_contract_version: number;
  amendment_status: string;
  idempotent_replay: boolean;
  new_contract_fingerprint: string | null;
  message: string;
}

const BASE_URL = '/api/v1';
const TOKEN_STORAGE_KEY = 'polaris_api_token';

export function getApiToken(): string {
  if (typeof window === 'undefined') return '';
  return localStorage.getItem(TOKEN_STORAGE_KEY) || '';
}

export function setApiToken(token: string): void {
  if (typeof window === 'undefined') return;
  const trimmed = token.trim();
  if (trimmed) {
    localStorage.setItem(TOKEN_STORAGE_KEY, trimmed);
  } else {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
  }
}

function authHeaders(extra?: HeadersInit): HeadersInit {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  const token = getApiToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return { ...headers, ...(extra as Record<string, string> | undefined) };
}

async function parseError(response: Response, fallback: string): Promise<never> {
  let detail = fallback;
  try {
    const body = await response.json();
    if (typeof body?.detail === 'string') {
      detail = body.detail;
    } else if (body?.detail?.message) {
      detail = body.detail.message;
    } else if (body?.detail?.error_code) {
      detail = `${body.detail.error_code}: ${body.detail.message || fallback}`;
    } else if (body?.message) {
      detail = body.message;
    }
  } catch {
    /* keep fallback */
  }
  throw new Error(`${detail} (HTTP ${response.status})`);
}

export async function registerSimulation(profile: UserProfile): Promise<{
  simulation_id: string;
  quantum_mountain_coordinates: { x: number; y: number };
  user_profile: UserProfile;
  active_contract_id?: string;
  active_contract_version?: number;
}> {
  const response = await fetch(`${BASE_URL}/simulation/register`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(profile),
  });
  if (!response.ok) await parseError(response, 'Failed to register simulation session');
  return response.json();
}

export async function evaluateDecision(payload: {
  simulation_id: string;
  intent_vector: Vector2D;
  declared_constraints: string[];
  active_storms: string[];
  custom_icebergs?: unknown[];
  custom_opposing_pairs?: [string, string][];
  request_id?: string;
}): Promise<EvaluateDecisionResponse> {
  const response = await fetch(`${BASE_URL}/simulation/evaluate-decision`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(payload),
  });
  if (!response.ok) await parseError(response, 'Failed to evaluate turn decision');
  return response.json();
}

export async function resumeSimulation(
  simulationId: string,
  payload: ResumeSimulationRequest
): Promise<ResumeSimulationResponse> {
  const response = await fetch(`${BASE_URL}/simulation/${simulationId}/resume`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(payload),
  });
  if (!response.ok) await parseError(response, 'Failed to resume simulation');
  return response.json();
}

export async function injectStorm(simulationId: string, storm: EnvironmentStorm): Promise<unknown> {
  const response = await fetch(`${BASE_URL}/simulation/${simulationId}/inject-storm`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(storm),
  });
  if (!response.ok) await parseError(response, 'Failed to inject custom storm');
  return response.json();
}

export async function getHistory(simulationId: string): Promise<SimulationHistoryResponse> {
  const response = await fetch(`${BASE_URL}/simulation/${simulationId}/history`, {
    headers: authHeaders(),
  });
  if (!response.ok) await parseError(response, 'Failed to fetch path history logs');
  return response.json();
}

export async function submitChangeRequest(payload: {
  simulation_id: string;
  request_id: string;
  natural_language_request: string;
  expected_goal_contract_version: number;
  actor_id?: string;
  explicit_change_intent?: string;
}): Promise<ChangeRequestResponse> {
  const response = await fetch(`${BASE_URL}/simulation/change-requests`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(payload),
  });
  if (!response.ok) await parseError(response, 'Failed to submit change request');
  return response.json();
}

export async function evaluateChangeRequest(
  requestId: string,
  actorId?: string
): Promise<DriftEvaluationResult> {
  const response = await fetch(`${BASE_URL}/simulation/change-requests/${requestId}/evaluate`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(actorId ? { actor_id: actorId } : {}),
  });
  if (!response.ok) await parseError(response, 'Failed to evaluate change request');
  return response.json();
}

export async function confirmChangeRequest(
  requestId: string,
  payload: { actor_id: string; decision: 'APPROVE' | 'REJECT'; rationale?: string }
): Promise<ConfirmAmendmentResponse> {
  const response = await fetch(`${BASE_URL}/simulation/change-requests/${requestId}/confirm`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(payload),
  });
  if (!response.ok) await parseError(response, 'Failed to confirm amendment decision');
  return response.json();
}
