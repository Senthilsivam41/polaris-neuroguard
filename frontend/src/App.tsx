import { Compass, Navigation } from 'lucide-react';
import { useSimulationStore } from './store/useSimulationStore';
import ControlPanel from './components/cockpit/ControlPanel';
import TacticalMap from './components/cockpit/TacticalMap';
import TelemetryAnalytics from './components/cockpit/TelemetryAnalytics';
import FractureModal from './components/cockpit/FractureModal';
import AmendmentPanel from './components/cockpit/AmendmentPanel';

export default function App() {
  const store = useSimulationStore();

  const accumulatedBurn = store.historyLogs.reduce((acc, curr) => acc + curr.telemetry_snapshot.actual_burn_rate, 0);

  return (
    <div className="h-screen w-screen bg-cyber-navy text-slate-100 flex flex-col font-sans overflow-hidden">
      {/* 🧭 Header */}
      <header className="border-b border-[#2A3754] bg-[#0E1422] px-6 py-3 flex items-center justify-between shadow-lg flex-shrink-0">
        <div className="flex items-center space-x-3">
          <Compass className="w-7 h-7 text-accent-cyan animate-pulse" />
          <div>
            <h1 className="text-base font-bold tracking-wider text-slate-100">POLARIS NEURO GUARD</h1>
            <p className="text-[10px] text-slate-400 font-mono">Neuro-Symbolic Multi-Agent Decision Guardrail</p>
          </div>
        </div>

        <div className="flex items-center space-x-6 font-mono text-xs">
          <div className="flex items-center space-x-2">
            <span className="text-slate-400">SESSION:</span>
            <span className="text-accent-cyan truncate w-32" title={store.currentSimulationId}>{store.currentSimulationId}</span>
          </div>
          <div className="flex items-center space-x-2">
            <span className="text-slate-400">STATUS:</span>
            <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
              store.currentSimulationId !== 'Not Initialized'
                ? "bg-emerald-950/40 border-emerald-500/30 text-emerald-400"
                : "bg-slate-950/40 border-slate-700/30 text-slate-400"
            }`}>
              {store.currentSimulationId !== 'Not Initialized' ? "ONLINE" : "STANDBY"}
            </span>
          </div>
        </div>
      </header>

      {/* ⚙️ Three-Column Workspace Layout (25% Left, 50% Center, 25% Right) */}
      <div className="flex-1 flex overflow-hidden p-6 gap-6">
        
        {/* Left Column (25%): Onboarding & Control Panel */}
        <aside className="w-1/4 flex flex-col flex-shrink-0">
          <ControlPanel />
        </aside>

        {/* Center Column (50%): Trajectory Telemetry & History Path Timeline */}
        <main className="w-1/2 flex flex-col bg-midnight-surface border border-[#2A3754] rounded-lg shadow-xl p-5 overflow-hidden justify-between">
          <div className="flex items-center space-x-2 border-b border-[#2A3754] pb-2 flex-shrink-0">
            <Navigation className="w-4 h-4 text-accent-cyan" />
            <h2 className="font-semibold text-xs tracking-wider text-slate-200 uppercase">Trajectory & Resultant Path</h2>
          </div>

          {/* Telemetry Grid */}
          <div className="mt-4 bg-[#0E1422] border border-[#2A3754] rounded p-3 grid grid-cols-2 gap-3 text-[11px] font-mono flex-shrink-0">
            <div>
              <span className="block text-slate-500 mb-0.5 uppercase tracking-widest text-[9px]">Coordinates</span>
              <span className="text-xs font-bold text-accent-cyan">
                X: {store.telemetryState?.current_position.x.toFixed(2) ?? "0.00"}, Y: {store.telemetryState?.current_position.y.toFixed(2) ?? "0.00"}
              </span>
            </div>
            <div>
              <span className="block text-slate-500 mb-0.5 uppercase tracking-widest text-[9px]">Accumulated Cost</span>
              <span className="text-xs font-bold text-slate-100">${accumulatedBurn.toFixed(0)} USD</span>
            </div>
            <div>
              <span className="block text-slate-500 mb-0.5 uppercase tracking-widest text-[9px]">Strategic Drift Delta</span>
              <span className={`text-xs font-bold ${store.isDrifting ? "text-alert-crimson" : "text-slate-100"}`}>
                {store.telemetryState?.angular_drift_delta.toFixed(2) ?? "0.00"}°
              </span>
            </div>
            <div>
              <span className="block text-slate-500 mb-0.5 uppercase tracking-widest text-[9px]">Simulation Status</span>
              <span className={`text-[10px] px-1.5 py-0.5 rounded font-bold inline-block border ${
                store.status === "PAUSED_BY_GUARDRAIL"
                  ? "bg-red-950/40 border-alert-crimson/30 text-alert-crimson font-bold"
                  : store.status === "RUNNING"
                  ? "bg-emerald-950/40 border-emerald-500/30 text-emerald-400"
                  : "bg-slate-950/40 border-slate-700/30 text-slate-400"
              }`}>
                {store.status}
              </span>
            </div>
          </div>

          {/* Tactical Map Visualization */}
          <div className="mt-4 flex-1 flex flex-col overflow-hidden">
            <TacticalMap />
          </div>

          {/* Path Timeline */}
          <div className="h-[150px] flex flex-col overflow-hidden mt-4 flex-shrink-0">
            <h3 className="text-xs font-bold text-accent-cyan tracking-widest uppercase mb-2 flex-shrink-0">Historical Trajectory Timeline</h3>
            
            <div className="flex-1 border border-[#2A3754] bg-[#0E1422] rounded p-3 text-xs font-mono overflow-y-auto">
              {store.historyLogs.length === 0 ? (
                <div className="h-full w-full flex items-center justify-center text-slate-500 select-none text-[11px]">
                  No steering decisions processed. Trigger Option A/B in the Cockpit.
                </div>
              ) : (
                <div className="space-y-2">
                  {[...store.historyLogs].reverse().map((log) => (
                    <div key={log.turn_number} className="border-b border-[#2A3754]/40 pb-2 mb-2 last:border-0 last:pb-0 last:mb-0">
                      <div className="flex justify-between font-bold text-slate-300 mb-1">
                        <span className="text-accent-cyan">TURN {log.turn_number}</span>
                        <span>POS: ({log.telemetry_snapshot.current_position.x.toFixed(1)}, {log.telemetry_snapshot.current_position.y.toFixed(1)})</span>
                      </div>
                      <div className="grid grid-cols-2 gap-2 text-[10px] text-slate-400">
                        <div>
                          <p><span className="text-slate-600">STEERING INTENT:</span> mag={log.applied_decision.intent_vector.magnitude.toFixed(1)} @ {log.applied_decision.intent_vector.heading_degrees.toFixed(1)}°</p>
                          <p><span className="text-slate-600">DRIFT DELTA:</span> {log.telemetry_snapshot.angular_drift_delta.toFixed(2)}°</p>
                        </div>
                        <div>
                          <p><span className="text-slate-600">ACTIVE STORMS:</span> {log.active_storms.join(', ') || 'None'}</p>
                          <p><span className="text-slate-600">BURN RATE:</span> ${log.telemetry_snapshot.actual_burn_rate.toFixed(0)} USD</p>
                        </div>
                      </div>
                      {log.fracture_events.active_constraints.length > 0 && (
                        <div className="mt-1 flex flex-wrap gap-1">
                          {log.fracture_events.active_constraints.map((c) => (
                            <span key={c} className="px-1.5 py-0.5 rounded bg-red-950/20 border border-alert-crimson/20 text-alert-crimson text-[9px] font-bold">
                              {c}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </main>

        {/* Right Column (25%): Telemetry Analytics */}
        <aside className="w-1/4 flex flex-col bg-midnight-surface border border-[#2A3754] rounded-lg shadow-xl p-5 overflow-y-auto flex-shrink-0">
          <div className="flex items-center space-x-2 border-b border-[#2A3754] pb-3 mb-4 flex-shrink-0">
            <Compass className="w-4 h-4 text-accent-cyan" />
            <h2 className="font-semibold text-xs tracking-wider text-slate-200 uppercase">Telemetry & Diagnostics</h2>
          </div>
          
          <TelemetryAnalytics />
          <AmendmentPanel />
          {store.actionError && store.currentSimulationId !== 'Not Initialized' && (
            <p className="mt-3 text-[10px] font-mono text-alert-crimson">{store.actionError}</p>
          )}
        </aside>

      </div>

      {/* ⚡ ADK 2.0 Human-in-the-Loop Intercept Modal */}
      <FractureModal />

      {/* Footer */}
      <footer className="border-t border-[#2A3754] bg-[#0E1422] py-2 text-center text-[10px] text-slate-500 font-mono flex-shrink-0">
        Polaris Neuro Guard Engine v2.0 • YAGNI Design Systems
      </footer>
    </div>
  );
}
