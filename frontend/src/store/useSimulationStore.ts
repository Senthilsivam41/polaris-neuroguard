import { create } from 'zustand';
import * as api from '../services/api';

interface SimulationStore {
  currentSimulationId: string;
  currentTurn: number;
  userProfile: api.UserProfile | null;
  mountainCoordinates: { x: number; y: number } | null;
  telemetryState: api.ShipTelemetry | null;
  activeStorms: string[];
  isDrifting: boolean;
  isDeadlocked: boolean;
  historyLogs: api.HistoryStepLog[];
  hitlData: api.HITLInterceptionData | null;
  activeConstraints: string[];
  collisionThreats: string[];
  status: string;
  apiToken: string;
  activeContractId: string | null;
  activeContractVersion: number;
  lastIntent: api.Vector2D | null;
  lastConstraints: string[];
  amendmentRequestId: string | null;
  amendmentEvaluation: api.DriftEvaluationResult | null;
  amendmentMessage: string | null;
  actionError: string | null;
  isResuming: boolean;
  isAmending: boolean;

  setApiToken: (token: string) => void;
  initializeSession: (profile: api.UserProfile) => Promise<string>;
  submitCTODecision: (intentVector: api.Vector2D, declaredConstraints: string[]) => Promise<void>;
  triggerStorm: (storm: api.EnvironmentStorm) => Promise<void>;
  fetchHistory: () => Promise<void>;
  resumeFromGuardrail: (resolutionAction: string, clearedConstraints?: string[]) => Promise<void>;
  clearHITL: () => void;
  submitAmendmentDraft: (naturalLanguageRequest: string) => Promise<void>;
  decideAmendment: (decision: 'APPROVE' | 'REJECT', rationale?: string) => Promise<void>;
  clearActionError: () => void;
}

function newId(prefix: string): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export const useSimulationStore = create<SimulationStore>((set, get) => ({
  currentSimulationId: 'Not Initialized',
  currentTurn: 0,
  userProfile: null,
  mountainCoordinates: null,
  telemetryState: null,
  activeStorms: [],
  isDrifting: false,
  isDeadlocked: false,
  historyLogs: [],
  hitlData: null,
  activeConstraints: [],
  collisionThreats: [],
  status: 'IDLE',
  apiToken: api.getApiToken() || 'dev-local-token',
  activeContractId: null,
  activeContractVersion: 1,
  lastIntent: null,
  lastConstraints: [],
  amendmentRequestId: null,
  amendmentEvaluation: null,
  amendmentMessage: null,
  actionError: null,
  isResuming: false,
  isAmending: false,

  setApiToken: (token) => {
    api.setApiToken(token);
    set({ apiToken: token.trim() });
  },

  clearActionError: () => set({ actionError: null }),

  initializeSession: async (profile) => {
    set({ actionError: null });
    api.setApiToken(get().apiToken);
    try {
      const res = await api.registerSimulation(profile);
      set({
        currentSimulationId: res.simulation_id,
        currentTurn: 0,
        userProfile: res.user_profile,
        mountainCoordinates: res.quantum_mountain_coordinates,
        telemetryState: {
          current_position: { x: 0.0, y: 0.0 },
          intent_vector: { magnitude: 0.0, heading_degrees: 0.0 },
          resultant_vector: { magnitude: 0.0, heading_degrees: 0.0 },
          actual_burn_rate: 0.0,
          angular_drift_delta: 0.0,
        },
        activeStorms: [],
        isDrifting: false,
        isDeadlocked: false,
        historyLogs: [],
        hitlData: null,
        activeConstraints: [],
        collisionThreats: [],
        status: 'RUNNING',
        activeContractId: res.active_contract_id ?? `contract-${res.simulation_id}`,
        activeContractVersion: res.active_contract_version ?? 1,
        lastIntent: null,
        lastConstraints: [],
        amendmentRequestId: null,
        amendmentEvaluation: null,
        amendmentMessage: null,
      });
      return res.simulation_id;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Registration failed';
      set({ actionError: message });
      throw err;
    }
  },

  submitCTODecision: async (intentVector, declaredConstraints) => {
    const simId = get().currentSimulationId;
    if (simId === 'Not Initialized') return;
    set({ actionError: null, lastIntent: intentVector, lastConstraints: declaredConstraints });

    try {
      const res = await api.evaluateDecision({
        simulation_id: simId,
        intent_vector: intentVector,
        declared_constraints: declaredConstraints,
        active_storms: get().activeStorms,
        request_id: newId('eval'),
      });

      set((state) => ({
        currentTurn: state.currentTurn + 1,
        telemetryState: res.telemetry,
        isDrifting: res.drift_warning,
        isDeadlocked: res.deadlocks.length > 0,
        hitlData: res.hitl_interception_data,
        activeConstraints: res.active_constraints,
        collisionThreats: res.collision_threats,
        status: res.status,
      }));

      await get().fetchHistory();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Decision evaluation failed';
      set({ actionError: message });
      throw err;
    }
  },

  triggerStorm: async (storm) => {
    const simId = get().currentSimulationId;
    if (simId === 'Not Initialized') return;
    set({ actionError: null });

    try {
      await api.injectStorm(simId, storm);
      set((state) => {
        const exists = state.activeStorms.includes(storm.name);
        return {
          activeStorms: exists ? state.activeStorms : [...state.activeStorms, storm.name],
        };
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Storm injection failed';
      set({ actionError: message });
      throw err;
    }
  },

  fetchHistory: async () => {
    const simId = get().currentSimulationId;
    if (simId === 'Not Initialized') return;

    const res = await api.getHistory(simId);
    set({ historyLogs: res.history });
  },

  resumeFromGuardrail: async (resolutionAction, clearedConstraints = []) => {
    const state = get();
    const simId = state.currentSimulationId;
    const hitl = state.hitlData;
    const profile = state.userProfile;
    if (simId === 'Not Initialized' || !hitl || !profile) return;
    if (!hitl.checkpoint_id || !hitl.checkpoint_version) {
      set({ actionError: 'Missing checkpoint metadata; cannot resume. Re-trigger a guarded turn.' });
      return;
    }

    set({ isResuming: true, actionError: null });
    try {
      const res = await api.resumeSimulation(simId, {
        checkpoint_id: hitl.checkpoint_id,
        resume_request_id: newId('resume'),
        actor_id: profile.user_id,
        resolution_action: resolutionAction,
        expected_checkpoint_version: hitl.checkpoint_version,
        intent_vector: state.lastIntent ?? state.telemetryState?.intent_vector,
        declared_constraints: clearedConstraints,
      });

      const remaining = res.remaining_interruption_details;
      const stillPaused = res.resume_status === 'PAUSED_BY_GUARDRAIL';
      set({
        telemetryState: res.telemetry,
        status: res.resume_status,
        activeContractVersion: res.active_contract_version,
        hitlData: stillPaused
          ? {
              requires_intervention: true,
              reason:
                (remaining?.explanation as string) ||
                (remaining?.reason as string) ||
                'Simulation remains paused by guardrail.',
              telemetry_snapshot: (remaining?.safe_telemetry_snapshot as api.HITLInterceptionData['telemetry_snapshot']) || {},
              checkpoint_id: (remaining?.checkpoint_id as string) || null,
              checkpoint_version: (remaining?.checkpoint_version as number) || null,
            }
          : null,
        lastConstraints: clearedConstraints,
        isDeadlocked: false,
        activeConstraints: stillPaused ? state.activeConstraints : [],
        collisionThreats: stillPaused ? state.collisionThreats : [],
      });
      await get().fetchHistory();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Resume failed';
      set({ actionError: message });
      throw err;
    } finally {
      set({ isResuming: false });
    }
  },

  clearHITL: () => {
    set({
      hitlData: null,
      status: 'RUNNING',
    });
  },

  submitAmendmentDraft: async (naturalLanguageRequest) => {
    const state = get();
    const simId = state.currentSimulationId;
    const profile = state.userProfile;
    if (simId === 'Not Initialized' || !profile) return;
    set({ isAmending: true, actionError: null, amendmentMessage: null });

    try {
      const requestId = newId('cr');
      await api.submitChangeRequest({
        simulation_id: simId,
        request_id: requestId,
        natural_language_request: naturalLanguageRequest,
        expected_goal_contract_version: state.activeContractVersion,
        actor_id: profile.user_id,
      });
      const evaluation = await api.evaluateChangeRequest(requestId, profile.user_id);
      set({
        amendmentRequestId: requestId,
        amendmentEvaluation: evaluation,
        amendmentMessage: `Evaluated as ${evaluation.recommended_action || evaluation.classification_status || 'PENDING'}`,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Amendment evaluation failed';
      set({ actionError: message });
      throw err;
    } finally {
      set({ isAmending: false });
    }
  },

  decideAmendment: async (decision, rationale = '') => {
    const state = get();
    const profile = state.userProfile;
    const requestId = state.amendmentRequestId;
    if (!profile || !requestId) return;
    set({ isAmending: true, actionError: null });

    try {
      const result = await api.confirmChangeRequest(requestId, {
        actor_id: profile.user_id,
        decision,
        rationale,
      });
      set({
        activeContractVersion: result.active_contract_version,
        amendmentMessage: result.message,
        amendmentEvaluation: decision === 'APPROVE' ? null : state.amendmentEvaluation,
        amendmentRequestId: decision === 'APPROVE' ? null : requestId,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Amendment decision failed';
      set({ actionError: message });
      throw err;
    } finally {
      set({ isAmending: false });
    }
  },
}));
