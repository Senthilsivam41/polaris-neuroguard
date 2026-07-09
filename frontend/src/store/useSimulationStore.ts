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

  initializeSession: (profile: api.UserProfile) => Promise<string>;
  submitCTODecision: (intentVector: api.Vector2D, declaredConstraints: string[]) => Promise<void>;
  triggerStorm: (storm: api.EnvironmentStorm) => Promise<void>;
  fetchHistory: () => Promise<void>;
  clearHITL: () => void;
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

  initializeSession: async (profile) => {
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
    });
    return res.simulation_id;
  },

  submitCTODecision: async (intentVector, declaredConstraints) => {
    const simId = get().currentSimulationId;
    if (simId === 'Not Initialized') return;

    const res = await api.evaluateDecision({
      simulation_id: simId,
      intent_vector: intentVector,
      declared_constraints: declaredConstraints,
      active_storms: get().activeStorms,
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

    // Refresh history logs after decision evaluation
    await get().fetchHistory();
  },

  triggerStorm: async (storm) => {
    const simId = get().currentSimulationId;
    if (simId === 'Not Initialized') return;

    await api.injectStorm(simId, storm);
    
    // Add to activeStorms array if not already present
    set((state) => {
      const exists = state.activeStorms.includes(storm.name);
      return {
        activeStorms: exists ? state.activeStorms : [...state.activeStorms, storm.name],
      };
    });
  },

  fetchHistory: async () => {
    const simId = get().currentSimulationId;
    if (simId === 'Not Initialized') return;

    const res = await api.getHistory(simId);
    set({
      historyLogs: res.history,
    });
  },

  clearHITL: () => {
    set({
      hitlData: null,
      status: 'RUNNING',
    });
  },
}));
