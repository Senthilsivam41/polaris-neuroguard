import { useSimulationStore } from '../../store/useSimulationStore';
import { Zap, Activity } from 'lucide-react';

export default function TelemetryAnalytics() {
  const store = useSimulationStore();
  const telemetry = store.telemetryState;
  
  // Calculate distance to Mountain (0, 1000)
  const x = telemetry?.current_position.x ?? 0.0;
  const y = telemetry?.current_position.y ?? 0.0;
  const distanceToMountain = Math.sqrt(x * x + (1000.0 - y) * (1000.0 - y));
  
  const velocity = telemetry?.resultant_vector.magnitude ?? 0.0;
  const accumulatedBurn = store.historyLogs.reduce((acc, curr) => acc + curr.telemetry_snapshot.actual_burn_rate, 0);

  // Generate dynamic drift diagnostics
  const driftReasons: string[] = [];
  if (store.isDrifting && telemetry) {
    driftReasons.push(`Drift threshold violated: Current track angle shifted by ${telemetry.angular_drift_delta.toFixed(2)}° from intent.`);
    if (store.activeStorms.length > 0) {
      driftReasons.push(`Active external storm forces: [${store.activeStorms.join(', ')}] introducing physical displacement.`);
    }
    driftReasons.push("CTO steering inputs are deflected by active weather vectors.");
  } else if (store.currentSimulationId !== 'Not Initialized') {
    driftReasons.push("Ship tracking is aligned with goal intent heading.");
    driftReasons.push("Angular drift delta remains within safe threshold (< 15°).");
  } else {
    driftReasons.push("Simulation standby. Lock in strategic roadmap to begin.");
  }

  return (
    <div className="space-y-4">
      {/* Sleek Monospace Speedometer Monitors Grid */}
      <div className="grid grid-cols-1 gap-2.5">
        
        {/* Metric 1: Velocity */}
        <div className="bg-[#0E1422] border border-[#2A3754] rounded p-2.5 font-mono text-xs relative overflow-hidden">
          <div className="absolute right-2 top-2">
            <Activity className="w-3.5 h-3.5 text-accent-cyan opacity-40 animate-pulse" />
          </div>
          <span className="block text-slate-500 uppercase tracking-widest text-[9px]">Actual Velocity</span>
          <span className="text-base font-bold text-accent-cyan">{velocity.toFixed(2)} kn/turn</span>
          <div className="w-full bg-[#182136] h-1.5 rounded-full overflow-hidden mt-1.5">
            <div 
              className="bg-accent-cyan h-full transition-all duration-500" 
              style={{ width: `${Math.min(100, (velocity / 25) * 100)}%` }} 
            />
          </div>
        </div>

        {/* Metric 2: Distance */}
        <div className="bg-[#0E1422] border border-[#2A3754] rounded p-2.5 font-mono text-xs relative overflow-hidden">
          <span className="block text-slate-500 uppercase tracking-widest text-[9px]">Distance to Mountain</span>
          <span className="text-base font-bold text-slate-100">{distanceToMountain.toFixed(2)} km</span>
          <div className="w-full bg-[#182136] h-1.5 rounded-full overflow-hidden mt-1.5">
            <div 
              className="bg-slate-300 h-full transition-all duration-500" 
              style={{ width: `${Math.max(0, Math.min(100, ((1000 - distanceToMountain) / 1000) * 100))}%` }} 
            />
          </div>
        </div>

        {/* Metric 3: Budget Status */}
        <div className="bg-[#0E1422] border border-[#2A3754] rounded p-2.5 font-mono text-xs relative overflow-hidden">
          <span className="block text-slate-500 uppercase tracking-widest text-[9px]">Accumulated Budget Spend</span>
          <span className="text-base font-bold text-slate-100">${accumulatedBurn.toFixed(0)} USD</span>
          {store.userProfile && (
            <div className="w-full bg-[#182136] h-1.5 rounded-full overflow-hidden mt-1.5">
              <div 
                className={`h-full transition-all duration-500 ${
                  store.activeConstraints.includes("BUDGET_OVERRUN") ? "bg-alert-crimson animate-pulse" : "bg-emerald-500"
                }`}
                style={{ width: `${Math.min(100, (accumulatedBurn / store.userProfile.anchor_goal.budget_limit_usd) * 100)}%` }} 
              />
            </div>
          )}
        </div>

      </div>

      {/* Drift Diagnostics Logs Panel */}
      <div className="space-y-2 border-t border-[#2A3754]/50 pt-3">
        <h4 className="text-xs font-bold text-slate-300 tracking-wider flex items-center space-x-1.5">
          <Zap className="w-3.5 h-3.5 text-accent-cyan" />
          <span>Drift Diagnostics</span>
        </h4>
        <div className="border border-[#2A3754] bg-[#0E1422] rounded p-2.5 text-[10px] font-mono space-y-1.5 max-h-[140px] overflow-y-auto">
          {driftReasons.map((reason, idx) => (
            <div key={idx} className="flex items-start space-x-1.5 border-b border-[#2A3754]/30 pb-1.5 last:border-0 last:pb-0">
              <span className={`w-1.5 h-1.5 rounded-full mt-1 flex-shrink-0 ${
                store.isDrifting ? "bg-alert-crimson" : "bg-accent-cyan"
              }`} />
              <p className="text-slate-400 leading-normal">{reason}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
