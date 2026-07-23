import { useState } from 'react';
import { useSimulationStore } from '../../store/useSimulationStore';
import { Shield, Wind, Zap, Play, CheckCircle2 } from 'lucide-react';
import { EnvironmentStorm } from '../../services/api';

interface DecisionOption {
  title: string;
  description: string;
  magnitude: number;
  heading: number;
}

function getDynamicOptions(industry: string, activeStorms: string[]): { optionA: DecisionOption; optionB: DecisionOption } {
  // Check active storms first for scenario specific options
  if (activeStorms.includes("Israel-Iraq Conflict")) {
    return {
      optionA: {
        title: "Absorb Surcharge",
        description: "Cruising speed (10 @ 0°), absorb Suez conflict surcharges",
        magnitude: 10.0,
        heading: 0.0
      },
      optionB: {
        title: "Evasive Reroute",
        description: "Reroute heading (12 @ 45°) to bypass Suez conflict",
        magnitude: 12.0,
        heading: 45.0
      }
    };
  }

  if (activeStorms.includes("Category 4 Cyclone")) {
    return {
      optionA: {
        title: "Penetrate Cyclone",
        description: "Sustain direct heading (10 @ 0°) through cyclone eye",
        magnitude: 10.0,
        heading: 0.0
      },
      optionB: {
        title: "Divert Course",
        description: "Divert course heading (12 @ 45°) around the storm",
        magnitude: 12.0,
        heading: 45.0
      }
    };
  }

  if (activeStorms.includes("Surging Petrol Prices")) {
    return {
      optionA: {
        title: "Sustain Cruising",
        description: "Full speed (10 @ 0°), absorb high petrol inflation",
        magnitude: 10.0,
        heading: 0.0
      },
      optionB: {
        title: "Eco Slow Steam",
        description: "Slow speed (7 @ 15°) to reduce burn rate (eco-mode)",
        magnitude: 7.0,
        heading: 15.0
      }
    };
  }

  // Fallback to industry-specific options if no storm is active
  switch (industry) {
    case "Fintech":
      return {
        optionA: {
          title: "Settle Ledgers",
          description: "Process payments (10 @ 0°) on primary network node",
          magnitude: 10.0,
          heading: 0.0
        },
        optionB: {
          title: "Vault Failover",
          description: "Sync transactions (12 @ 45°) to secondary vault",
          magnitude: 12.0,
          heading: 45.0
        }
      };
    case "Healthcare":
      return {
        optionA: {
          title: "EMR Database Sync",
          description: "Continuous syncing (10 @ 0°) of health records",
          magnitude: 10.0,
          heading: 0.0
        },
        optionB: {
          title: "Divert Clinic Queue",
          description: "Reroute patient intake logs (12 @ 45°) to region B",
          magnitude: 12.0,
          heading: 45.0
        }
      };
    case "Retail & E-commerce":
      return {
        optionA: {
          title: "Central Fulfill",
          description: "Dispatch orders (10 @ 0°) from central warehouse",
          magnitude: 10.0,
          heading: 0.0
        },
        optionB: {
          title: "Local Hub Route",
          description: "Distribute supply vectors (12 @ 45°) to local hubs",
          magnitude: 12.0,
          heading: 45.0
        }
      };
    case "Aerospace & Defense":
      return {
        optionA: {
          title: "Satellite Orbit",
          description: "Maintain orbital trajectory (10 @ 0°) via low satellites",
          magnitude: 10.0,
          heading: 0.0
        },
        optionB: {
          title: "Radar Guidance",
          description: "Transfer tracking vectors (12 @ 45°) to ground radar",
          magnitude: 12.0,
          heading: 45.0
        }
      };
    case "Energy & Utilities":
      return {
        optionA: {
          title: "Grid Load Match",
          description: "Transmit maximum load (10 @ 0°) across the grid",
          magnitude: 10.0,
          heading: 0.0
        },
        optionB: {
          title: "Renewable Shed",
          description: "Divert grid loads (12 @ 45°) to solar banks",
          magnitude: 12.0,
          heading: 45.0
        }
      };
    case "Maritime Logistics":
    default:
      return {
        optionA: {
          title: "Great Circle Path",
          description: "Sustain primary direct path (10 @ 0°) to destination",
          magnitude: 10.0,
          heading: 0.0
        },
        optionB: {
          title: "Cape detour",
          description: "Initiate steering deflection (12 @ 45°) detouring via Cape",
          magnitude: 12.0,
          heading: 45.0
        }
      };
  }
}

export default function ControlPanel() {
  const store = useSimulationStore();
  
  // Registration local form state
  const [userId, setUserId] = useState('user_dev_01');
  const [apiToken, setApiToken] = useState(store.apiToken || 'dev-local-token');
  const [role, setRole] = useState('Chief Technology Officer');
  const [companyScale, setCompanyScale] = useState('Enterprise');
  const [industry, setIndustry] = useState('Maritime Logistics');
  const [goalTitle, setGoalTitle] = useState('Container Ship Route Optimization');
  const [timeline, setTimeline] = useState(12);
  const [budget, setBudget] = useState(250.0); // Set low to trigger BUDGET_OVERRUN in Turn 2 of Scenario A
  const [sla, setSla] = useState(99.9);
  const [riskTolerance, setRiskTolerance] = useState<'Conservative' | 'Balanced' | 'Aggressive'>('Balanced');

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    store.setApiToken(apiToken);
    await store.initializeSession({
      user_id: userId,
      role: role,
      company_scale: companyScale,
      industry: industry,
      anchor_goal: {
        title: goalTitle,
        target_timeline_months: timeline,
        budget_limit_usd: budget,
        reliability_target_sla: sla,
      },
      risk_tolerance: riskTolerance,
    });
  };

  const handleInjectStorm = async (name: string, type: 'Geopolitical' | 'Meteorological' | 'Economic', magnitude: number, heading: number) => {
    const stormPayload: EnvironmentStorm = {
      storm_type: type,
      name: name,
      magnitude: magnitude,
      heading_degrees: heading
    };
    await store.triggerStorm(stormPayload);
  };

  const handleSubmitDecision = async (magnitude: number, heading: number) => {
    const constraints: string[] = [];
    if (deadlockSelected) {
      constraints.push("RIGID_TIMELINE", "FREEZE_HEADCOUNT");
    }
    await store.submitCTODecision({ magnitude, heading_degrees: heading }, constraints);
  };

  // State to simulate deadlocks selection in Option B
  const [deadlockSelected, setDeadlockSelected] = useState(false);

  // If session is not initialized yet, render User Onboarding
  if (store.currentSimulationId === 'Not Initialized') {
    return (
      <div className="flex-1 flex flex-col bg-midnight-surface border border-[#2A3754] rounded-lg shadow-xl p-5 overflow-y-auto">
        <div className="flex items-center space-x-2 border-b border-[#2A3754] pb-3 mb-4">
          <Shield className="w-5 h-5 text-accent-cyan" />
          <h2 className="font-semibold text-sm tracking-wider text-slate-200 uppercase">User Onboarding</h2>
        </div>

        <form onSubmit={handleRegister} className="flex-1 flex flex-col justify-between space-y-4 text-xs">
          <div className="space-y-3 overflow-y-auto pr-1">
            <div>
              <label className="block text-slate-400 mb-1">API Bearer Token</label>
              <input 
                type="password" 
                value={apiToken} 
                onChange={(e) => setApiToken(e.target.value)} 
                autoComplete="off"
                className="w-full bg-[#0E1422] border border-[#2A3754] rounded p-2 text-slate-100 focus:border-accent-cyan focus:outline-none font-mono" 
              />
              <p className="mt-1 text-[10px] text-slate-500 font-mono">Offline/mock default: dev-local-token</p>
            </div>
            <div>
              <label className="block text-slate-400 mb-1">User Identifier</label>
              <input 
                type="text" 
                value={userId} 
                onChange={(e) => setUserId(e.target.value)} 
                className="w-full bg-[#0E1422] border border-[#2A3754] rounded p-2 text-slate-100 focus:border-accent-cyan focus:outline-none" 
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-slate-400 mb-1">Organizational Role</label>
                <input 
                  type="text" 
                  value={role} 
                  onChange={(e) => setRole(e.target.value)} 
                  className="w-full bg-[#0E1422] border border-[#2A3754] rounded p-2 text-slate-100 focus:border-accent-cyan focus:outline-none" 
                />
              </div>
              <div>
                <label className="block text-slate-400 mb-1">Scale</label>
                <input 
                  type="text" 
                  value={companyScale} 
                  onChange={(e) => setCompanyScale(e.target.value)} 
                  className="w-full bg-[#0E1422] border border-[#2A3754] rounded p-2 text-slate-100 focus:border-accent-cyan focus:outline-none" 
                />
              </div>
            </div>
            <div>
              <label className="block text-slate-400 mb-1">Industry Sectors</label>
              <select 
                value={industry} 
                onChange={(e) => setIndustry(e.target.value)} 
                className="w-full bg-[#0E1422] border border-[#2A3754] rounded p-2 text-slate-100 focus:border-accent-cyan focus:outline-none" 
              >
                <option value="Maritime Logistics">Maritime Logistics</option>
                <option value="Fintech">Fintech</option>
                <option value="Healthcare">Healthcare</option>
                <option value="Retail & E-commerce">Retail & E-commerce</option>
                <option value="Aerospace & Defense">Aerospace & Defense</option>
                <option value="Energy & Utilities">Energy & Utilities</option>
              </select>
            </div>

            <div className="border-t border-[#2A3754]/50 pt-3 mt-3">
              <h3 className="text-accent-cyan font-bold mb-2 tracking-widest uppercase text-[10px]">Anchor Goal Specifications</h3>
              <div className="space-y-2">
                <div>
                  <label className="block text-slate-400 mb-1">Goal Objective Title</label>
                  <input 
                    type="text" 
                    value={goalTitle} 
                    onChange={(e) => setGoalTitle(e.target.value)} 
                    className="w-full bg-[#0E1422] border border-[#2A3754] rounded p-2 text-slate-100 focus:border-accent-cyan focus:outline-none" 
                  />
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <div>
                    <label className="block text-slate-400 mb-1">Timeline (M)</label>
                    <input 
                      type="number" 
                      value={timeline} 
                      onChange={(e) => setTimeline(Number(e.target.value))} 
                      className="w-full bg-[#0E1422] border border-[#2A3754] rounded p-2 text-slate-100 focus:border-accent-cyan focus:outline-none" 
                    />
                  </div>
                  <div>
                    <label className="block text-slate-400 mb-1">Budget ($)</label>
                    <input 
                      type="number" 
                      value={budget} 
                      onChange={(e) => setBudget(Number(e.target.value))} 
                      className="w-full bg-[#0E1422] border border-[#2A3754] rounded p-2 text-slate-100 focus:border-accent-cyan focus:outline-none" 
                    />
                  </div>
                  <div>
                    <label className="block text-slate-400 mb-1">SLA Target (%)</label>
                    <input 
                      type="number" 
                      step="0.01"
                      value={sla} 
                      onChange={(e) => setSla(Number(e.target.value))} 
                      className="w-full bg-[#0E1422] border border-[#2A3754] rounded p-2 text-slate-100 focus:border-accent-cyan focus:outline-none" 
                    />
                  </div>
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">Risk Tolerance Mode</label>
                  <select 
                    value={riskTolerance} 
                    onChange={(e) => setRiskTolerance(e.target.value as any)}
                    className="w-full bg-[#0E1422] border border-[#2A3754] rounded p-2 text-slate-100 focus:border-accent-cyan focus:outline-none"
                  >
                    <option value="Conservative">Conservative</option>
                    <option value="Balanced">Balanced</option>
                    <option value="Aggressive">Aggressive</option>
                  </select>
                </div>
              </div>
            </div>
          </div>

          {store.actionError && (
            <p className="text-[10px] text-alert-crimson font-mono">{store.actionError}</p>
          )}

          <button 
            type="submit" 
            className="w-full bg-accent-cyan hover:bg-[#00B8D4] text-[#0B0F19] hover:shadow-cyan-glow text-xs font-bold font-mono py-2.5 rounded transition-all flex items-center justify-center space-x-2 border border-accent-cyan/30"
          >
            <Play className="w-4 h-4 fill-current" />
            <span>LOCK IN STRATEGIC ROADMAP</span>
          </button>
        </form>
      </div>
    );
  }

  // Active Session Layout
  const profile = store.userProfile!;
  const options = getDynamicOptions(profile.industry, store.activeStorms);

  return (
    <div className="flex-1 flex flex-col bg-midnight-surface border border-[#2A3754] rounded-lg shadow-xl p-5 overflow-hidden justify-between">
      {/* 1. Profile Metadata Display Card */}
      <div className="space-y-3">
        <div className="flex items-center space-x-2 border-b border-[#2A3754] pb-2">
          <Shield className="w-4 h-4 text-accent-cyan" />
          <h2 className="font-semibold text-xs tracking-wider text-slate-200 uppercase">1. Strategic User Profile</h2>
        </div>

        <div className="bg-[#0E1422] border border-[#2A3754] rounded p-3 text-[11px] font-mono space-y-2 relative overflow-hidden">
          <div className="absolute top-0 right-0 w-16 h-16 border-t-2 border-r-2 border-accent-cyan/15 pointer-events-none rounded-tr" />
          <div className="flex justify-between">
            <span className="text-slate-500">USER / ROLE:</span>
            <span className="text-slate-300 font-bold">{profile.user_id} ({profile.role})</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">INDUSTRY / SCALE:</span>
            <span className="text-slate-300">{profile.industry} • {profile.company_scale}</span>
          </div>
          <div className="flex justify-between border-t border-[#2A3754]/40 pt-1.5 mt-1.5">
            <span className="text-slate-500">ANCHOR TARGET:</span>
            <span className="text-accent-cyan font-bold truncate max-w-[140px]" title={profile.anchor_goal.title}>{profile.anchor_goal.title}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">BUDGET BOUND:</span>
            <span className="text-slate-300">${profile.anchor_goal.budget_limit_usd.toFixed(0)} USD</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">TIMELINE / SLA:</span>
            <span className="text-slate-300">{profile.anchor_goal.target_timeline_months} Mos / {profile.anchor_goal.reliability_target_sla}%</span>
          </div>
        </div>
      </div>

      {/* 2. Interactive Environmental Storm Injector Grid */}
      <div className="space-y-3 pt-3 border-t border-[#2A3754]/50">
        <div className="flex items-center space-x-2 border-b border-[#2A3754] pb-2">
          <Wind className="w-4 h-4 text-accent-cyan" />
          <h2 className="font-semibold text-xs tracking-wider text-slate-200 uppercase">2. Environmental Storm Injector</h2>
        </div>

        <div className="grid grid-cols-1 gap-2 text-xs">
          {/* Storm A */}
          <button 
            onClick={() => handleInjectStorm("Israel-Iraq Conflict", "Geopolitical", 5.0, 180.0)}
            className={`w-full p-2.5 rounded border text-left font-mono flex items-center justify-between transition-all ${
              store.activeStorms.includes("Israel-Iraq Conflict")
                ? "bg-red-950/20 border-alert-crimson/50 text-alert-crimson"
                : "bg-[#0E1422] border-[#2A3754] hover:border-slate-500 text-slate-300"
            }`}
          >
            <div>
              <p className="font-bold">Israel-Iraq Conflict</p>
              <p className="text-[10px] text-slate-500">Geopolitical Headwind (5.0 @ 180°)</p>
            </div>
            {store.activeStorms.includes("Israel-Iraq Conflict") && <CheckCircle2 className="w-4 h-4 text-alert-crimson" />}
          </button>

          {/* Storm B */}
          <button 
            onClick={() => handleInjectStorm("Category 4 Cyclone", "Meteorological", 12.0, 90.0)}
            className={`w-full p-2.5 rounded border text-left font-mono flex items-center justify-between transition-all ${
              store.activeStorms.includes("Category 4 Cyclone")
                ? "bg-red-950/20 border-alert-crimson/50 text-alert-crimson"
                : "bg-[#0E1422] border-[#2A3754] hover:border-slate-500 text-slate-300"
            }`}
          >
            <div>
              <p className="font-bold">Category 4 Cyclone</p>
              <p className="text-[10px] text-slate-500">Meteorological Crosswind (12.0 @ 90°)</p>
            </div>
            {store.activeStorms.includes("Category 4 Cyclone") && <CheckCircle2 className="w-4 h-4 text-alert-crimson" />}
          </button>

          {/* Storm C */}
          <button 
            onClick={() => handleInjectStorm("Surging Petrol Prices", "Economic", 0.0, 0.0)}
            className={`w-full p-2.5 rounded border text-left font-mono flex items-center justify-between transition-all ${
              store.activeStorms.includes("Surging Petrol Prices")
                ? "bg-red-950/20 border-alert-crimson/50 text-alert-crimson"
                : "bg-[#0E1422] border-[#2A3754] hover:border-slate-500 text-slate-300"
            }`}
          >
            <div>
              <p className="font-bold">Surging Petrol Prices</p>
              <p className="text-[10px] text-slate-500">Economic Surcharge (1.35x multiplier)</p>
            </div>
            {store.activeStorms.includes("Surging Petrol Prices") && <CheckCircle2 className="w-4 h-4 text-alert-crimson" />}
          </button>
        </div>
      </div>

      {/* 3. Decision Terminal */}
      <div className="space-y-3 pt-3 border-t border-[#2A3754]/50">
        <div className="flex items-center justify-between border-b border-[#2A3754] pb-2">
          <div className="flex items-center space-x-2">
            <Zap className="w-4 h-4 text-accent-cyan" />
            <h2 className="font-semibold text-xs tracking-wider text-slate-200 uppercase">3. Decision Terminal</h2>
          </div>
          {/* Deadlock switch simulator */}
          <label className="flex items-center space-x-1.5 cursor-pointer text-[10px] font-mono text-slate-500 select-none">
            <input 
              type="checkbox" 
              checked={deadlockSelected} 
              onChange={(e) => setDeadlockSelected(e.target.checked)} 
              className="accent-accent-cyan" 
            />
            <span>Inject Deadlocks</span>
          </label>
        </div>

        <div className="grid grid-cols-2 gap-2 text-xs font-mono">
          <button 
            onClick={() => handleSubmitDecision(options.optionA.magnitude, options.optionA.heading)}
            className="bg-[#0E1422] hover:bg-[#1C253B] border border-accent-cyan/20 hover:border-accent-cyan p-2.5 rounded text-center text-slate-200 transition-colors uppercase tracking-widest text-[9px] flex flex-col justify-between min-h-[60px]"
          >
            <p className="font-bold text-accent-cyan w-full text-center border-b border-[#2A3754]/50 pb-1 mb-1">{options.optionA.title}</p>
            <p className="text-[8px] text-slate-400 leading-tight normal-case text-left w-full">{options.optionA.description}</p>
          </button>

          <button 
            onClick={() => handleSubmitDecision(options.optionB.magnitude, options.optionB.heading)}
            className="bg-[#0E1422] hover:bg-[#1C253B] border border-accent-cyan/20 hover:border-accent-cyan p-2.5 rounded text-center text-slate-200 transition-colors uppercase tracking-widest text-[9px] flex flex-col justify-between min-h-[60px]"
          >
            <p className="font-bold text-accent-cyan w-full text-center border-b border-[#2A3754]/50 pb-1 mb-1">{options.optionB.title}</p>
            <p className="text-[8px] text-slate-400 leading-tight normal-case text-left w-full">{options.optionB.description}</p>
          </button>
        </div>
      </div>
    </div>
  );
}
