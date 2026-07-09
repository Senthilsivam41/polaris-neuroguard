import { useSimulationStore } from '../../store/useSimulationStore';
import { ShieldAlert, RefreshCw, XCircle, Goal } from 'lucide-react';

export default function FractureModal() {
  const store = useSimulationStore();
  const hitl = store.hitlData;

  if (!hitl) return null;

  const profile = store.userProfile;

  return (
    <div className="fixed inset-0 bg-red-950/80 backdrop-blur-md z-50 flex items-center justify-center p-6">
      
      {/* Inject custom shake style for the panel vibration */}
      <style>{`
        @keyframes shake {
          0%, 100% { transform: translate(0, 0); }
          10% { transform: translate(-2px, -1px); }
          20% { transform: translate(-1px, 2px); }
          30% { transform: translate(1px, -2px); }
          40% { transform: translate(-2px, 1px); }
          50% { transform: translate(2px, -1px); }
          60% { transform: translate(-1px, 2px); }
          70% { transform: translate(1px, 1px); }
          80% { transform: translate(-2px, -2px); }
          90% { transform: translate(2px, 1px); }
        }
        .vibrate-panel {
          animation: shake 0.25s infinite;
        }
      `}</style>

      <div className="bg-[#0E1422] border-2 border-alert-crimson shadow-2xl shadow-red-500/20 max-w-lg w-full rounded-lg p-6 flex flex-col space-y-5 text-center relative overflow-hidden vibrate-panel">
        
        {/* Warning Indicator */}
        <div className="flex justify-center">
          <ShieldAlert className="w-12 h-12 text-alert-crimson animate-bounce" />
        </div>

        <div className="space-y-1">
          <h2 className="text-sm font-bold tracking-widest text-alert-crimson uppercase">
            ADK 2.0 GUARDRAIL INTERCEPT
          </h2>
          <p className="text-[10px] text-slate-400 font-mono">
            Graph Execution Halted • SMT Verification Breach
          </p>
        </div>

        {/* Breach Description */}
        <div className="bg-red-950/20 border border-alert-crimson/30 rounded p-3 text-xs text-slate-300 font-mono text-left">
          <p className="font-bold text-alert-crimson mb-1 flex items-center space-x-1.5">
            <XCircle className="w-3.5 h-3.5" />
            <span>INTERCEPTION REASON:</span>
          </p>
          <p className="leading-relaxed text-slate-400">{hitl.reason}</p>
        </div>

        {/* Side-by-Side Contradiction & Goal Matrix */}
        <div className="grid grid-cols-2 gap-4 text-left text-xs font-mono">
          
          {/* Left Column: Contradiction Details */}
          <div className="bg-slate-950/40 border border-[#2A3754] rounded p-3 space-y-2">
            <h4 className="text-[10px] font-bold text-alert-crimson uppercase tracking-widest">
              Mathematical Defect
            </h4>
            <div className="text-[10px] space-y-1 text-slate-400">
              <p><span className="text-slate-600">DEADLOCKS:</span> {hitl.telemetry_snapshot.deadlocks.length > 0 ? "TRUE" : "FALSE"}</p>
              {hitl.telemetry_snapshot.deadlocks.map((pair: [string, string], i: number) => (
                <p key={i} className="text-alert-crimson font-bold">
                  {pair[0]} ⟷ {pair[1]}
                </p>
              ))}
              <p className="mt-1"><span className="text-slate-600">COLLISIONS:</span> {hitl.telemetry_snapshot.threats.length > 0 ? "TRUE" : "FALSE"}</p>
              {hitl.telemetry_snapshot.threats.map((threat: string, i: number) => (
                <p key={i} className="text-alert-crimson font-bold">
                  {threat}
                </p>
              ))}
            </div>
          </div>

          {/* Right Column: Original Anchor Goal Bounds */}
          <div className="bg-slate-950/40 border border-[#2A3754] rounded p-3 space-y-2">
            <h4 className="text-[10px] font-bold text-accent-cyan uppercase tracking-widest flex items-center space-x-1">
              <Goal className="w-3 h-3" />
              <span>Anchor Goals</span>
            </h4>
            {profile && (
              <div className="text-[10px] space-y-1 text-slate-400">
                <p className="text-slate-200 font-bold truncate">{profile.anchor_goal.title}</p>
                <p><span className="text-slate-600">BUDGET:</span> ${profile.anchor_goal.budget_limit_usd.toFixed(0)}</p>
                <p><span className="text-slate-600">TIMELINE:</span> {profile.anchor_goal.target_timeline_months}m</p>
                <p><span className="text-slate-600">SLA TARGET:</span> {profile.anchor_goal.reliability_target_sla}%</p>
              </div>
            )}
          </div>

        </div>

        {/* Remediate Action Button */}
        <button 
          onClick={() => store.clearHITL()}
          className="w-full bg-alert-crimson hover:bg-[#E62E5C] text-slate-100 font-mono font-bold text-xs py-2.5 rounded transition-colors flex items-center justify-center space-x-2 border border-alert-crimson/50"
        >
          <RefreshCw className="w-4 h-4" />
          <span>REMEDIATE PATH CONSTRAINTS</span>
        </button>

      </div>
    </div>
  );
}
