import { useState } from 'react';
import { useSimulationStore } from '../../store/useSimulationStore';
import { Maximize2, Minimize2 } from 'lucide-react';

export default function TacticalMap() {
  const store = useSimulationStore();
  const [zoomMode, setZoomMode] = useState<'tactical' | 'global'>('tactical');

  const position = store.telemetryState?.current_position ?? { x: 0.0, y: 0.0 };
  const heading = store.telemetryState?.resultant_vector.heading_degrees ?? 0.0;
  
  // Build coordinates path string starting from (0,0)
  const historyPoints = ["0,0", ...store.historyLogs.map(log => 
    `${log.telemetry_snapshot.current_position.x},${log.telemetry_snapshot.current_position.y}`
  )].join(' ');

  // Standard constraint icebergs
  const defaultIcebergs = [
    { name: "Budget Lockout", x: -50.0, y: 300.0, radius: 100.0 },
    { name: "Compliance Deadlock", x: 60.0, y: 600.0, radius: 100.0 },
    { name: "Schedule Slippage", x: 150.0, y: 200.0, radius: 100.0 },
    { name: "Scope Creep", x: -200.0, y: 100.0, radius: 100.0 }
  ];

  // Dynamic ViewBox calculations
  // global: fixed viewBox 700x1100, x: [-350, 350], y: [-50, 1050]
  // tactical: centered on ship, width: 300, height: 300, y: [pos.y - 50, pos.y + 250]
  const isTactical = zoomMode === 'tactical';
  const viewBoxX = isTactical ? position.x - 150 : -350;
  const viewBoxY = isTactical ? -(position.y + 250) : -1020;
  const viewBoxWidth = isTactical ? 300 : 700;
  const viewBoxHeight = isTactical ? 300 : 1100;

  // Dynamic stroke widths & font sizes depending on zoom mode
  const gridStroke = isTactical ? 0.4 : 0.8;
  const pathStroke = isTactical ? 1.5 : 3.5;
  const dotRadius = isTactical ? 2.5 : 4.5;
  const dotStroke = isTactical ? 1.2 : 2.5;
  const labelFontSize = isTactical ? 5 : 9;

  // Dynamic grid coordinates generation based on focus center
  const gridLinesY = isTactical 
    ? Array.from({ length: 9 }, (_, i) => Math.floor((position.y - 50) / 50) * 50 + i * 50)
    : [200, 400, 600, 800, 1000];

  const gridLinesX = isTactical
    ? Array.from({ length: 9 }, (_, i) => Math.floor((position.x - 150) / 50) * 50 + i * 50)
    : [-200, -100, 0, 100, 200];

  return (
    <div className="flex-1 flex flex-col overflow-hidden relative">
      
      {/* ⚙️ Zoom Mode Selector Toggle Overlay */}
      <div className="absolute top-3 right-3 z-10 flex space-x-1.5">
        <button 
          onClick={() => setZoomMode('tactical')}
          className={`px-2 py-1 rounded text-[9px] font-mono border flex items-center space-x-1 transition-all ${
            zoomMode === 'tactical'
              ? "bg-accent-cyan/20 border-accent-cyan text-accent-cyan font-bold"
              : "bg-[#0E1422]/90 border-[#2A3754] text-slate-400 hover:text-slate-200"
          }`}
          title="Zoom to active ship track"
        >
          <Minimize2 className="w-2.5 h-2.5" />
          <span>Tactical Radar</span>
        </button>
        <button 
          onClick={() => setZoomMode('global')}
          className={`px-2 py-1 rounded text-[9px] font-mono border flex items-center space-x-1 transition-all ${
            zoomMode === 'global'
              ? "bg-accent-cyan/20 border-accent-cyan text-accent-cyan font-bold"
              : "bg-[#0E1422]/90 border-[#2A3754] text-slate-400 hover:text-slate-200"
          }`}
          title="View full ocean graph target"
        >
          <Maximize2 className="w-2.5 h-2.5" />
          <span>Global Chart</span>
        </button>
      </div>

      <div className="flex-1 bg-[#090C14] border border-[#2A3754] rounded relative overflow-hidden flex items-center justify-center">
        
        {/* SVG Viewport */}
        <svg 
          viewBox={`${viewBoxX} ${viewBoxY} ${viewBoxWidth} ${viewBoxHeight}`} 
          className="w-full h-full max-h-[500px] select-none"
        >
          {/* Flip Y-axis to represent Cartesian coordinates (positive is up) */}
          <g transform="scale(1, -1)">
            
            {/* 🌐 Grid Lines & Labels */}
            {gridLinesY.map(y => (
              <g key={`grid-y-${y}`}>
                <line x1={viewBoxX} y1={y} x2={viewBoxX + viewBoxWidth} y2={y} stroke="#1B243B" strokeWidth={gridStroke} strokeDasharray="2 4" />
                <g transform={`translate(${viewBoxX + 10}, ${y}) scale(1, -1)`}>
                  <text fill="#475569" fontSize={labelFontSize} fontFamily="monospace" textAnchor="start">Y: {y}</text>
                </g>
              </g>
            ))}

            {gridLinesX.map(x => (
              <g key={`grid-x-${x}`}>
                <line x1={x} y1={-viewBoxY - viewBoxHeight} x2={x} y2={-viewBoxY} stroke="#1B243B" strokeWidth={gridStroke} strokeDasharray="2 4" />
                <g transform={`translate(${x}, ${-viewBoxY - viewBoxHeight + 10}) scale(1, -1)`}>
                  <text fill="#475569" fontSize={labelFontSize} fontFamily="monospace" textAnchor="middle">X: {x}</text>
                </g>
              </g>
            ))}

            {/* Starting Coordinate Indicator (0,0) */}
            <circle cx="0" cy="0" r={isTactical ? 2 : 5} fill="#1E293B" stroke="#475569" strokeWidth={isTactical ? 0.8 : 1.5} />
            <g transform={`translate(0, ${isTactical ? -8 : -15}) scale(1, -1)`}>
              <text fill="#64748B" fontSize={labelFontSize} fontFamily="monospace" textAnchor="middle">START (0,0)</text>
            </g>

            {/* 🏔️ The Quantum Mountain Target (0, 1000) */}
            <polygon 
              points={isTactical ? "-10,1000 10,1000 0,1015" : "-25,1000 25,1000 0,1050"} 
              fill="#161D30" 
              stroke="#00E5FF" 
              strokeWidth={isTactical ? 1.5 : 2.5} 
            />
            {/* Glimmer Beacon */}
            <circle cx="0" cy={isTactical ? 1015 : 1050} r={isTactical ? 2 : 4} fill="#00E5FF" className="animate-ping" />
            <circle cx="0" cy={isTactical ? 1015 : 1050} r={isTactical ? 1 : 2} fill="#00E5FF" />
            
            <g transform={`translate(0, ${isTactical ? 990 : 980}) scale(1, -1)`}>
              <text fill="#00E5FF" fontSize={labelFontSize} fontWeight="bold" fontFamily="monospace" textAnchor="middle">
                MOUNTAIN (0,1000)
              </text>
            </g>

            {/* 🧊 Constraint Icebergs (Floating hazards) */}
            {defaultIcebergs.map((ib) => (
              <g key={ib.name}>
                <circle 
                  cx={ib.x} 
                  cy={ib.y} 
                  r={ib.radius} 
                  fill="rgba(255, 51, 102, 0.03)" 
                  stroke={store.collisionThreats.includes(ib.name) ? "#FF3366" : "#2A3754"} 
                  strokeWidth={isTactical ? 0.6 : 1.2} 
                  strokeDasharray="4 3" 
                />
                <circle cx={ib.x} cy={ib.y} r={isTactical ? 1.5 : 3} fill={store.collisionThreats.includes(ib.name) ? "#FF3366" : "#475569"} />
                <g transform={`translate(${ib.x}, ${ib.y + (isTactical ? 6 : 12)}) scale(1, -1)`}>
                  <text 
                    fill={store.collisionThreats.includes(ib.name) ? "#FF3366" : "#64748B"} 
                    fontSize={labelFontSize} 
                    fontFamily="sans-serif" 
                    textAnchor="middle"
                    fontWeight={store.collisionThreats.includes(ib.name) ? "bold" : "normal"}
                  >
                    {ib.name.toUpperCase()}
                  </text>
                </g>
              </g>
            ))}

            {/* 🟢 Trajectory History Path (Bright Neon Green) */}
            <polyline 
              points={historyPoints} 
              fill="none" 
              stroke={store.isDrifting ? "#FF3366" : "#10F293"} 
              strokeWidth={pathStroke} 
              strokeLinecap="round"
              strokeLinejoin="round"
            />

            {/* Turn Nodes Circles */}
            {store.historyLogs.map((log) => (
              <circle 
                key={log.turn_number}
                cx={log.telemetry_snapshot.current_position.x} 
                cy={log.telemetry_snapshot.current_position.y} 
                r={dotRadius} 
                fill="#0E1422" 
                stroke={store.isDrifting ? "#FF3366" : "#10F293"} 
                strokeWidth={dotStroke} 
              />
            ))}

            {/* 🔵 Intent Path (Dotted line connecting ship straight to Mountain target) */}
            <line 
              x1={position.x} 
              y1={position.y} 
              x2="0" 
              y2="1000" 
              stroke="#00E5FF" 
              strokeWidth={isTactical ? 0.6 : 1.2} 
              strokeDasharray="4 4" 
              opacity="0.6"
            />

            {/* 🚀 The Ship (Delta Wing structure with rotation applied) */}
            <g transform={`translate(${position.x}, ${position.y}) rotate(${-heading})`}>
              <circle cx="0" cy="0" r={isTactical ? 6 : 14} fill="rgba(0, 229, 255, 0.15)" className="animate-pulse" />
              <polygon 
                points={isTactical ? "-4,-5 4,-5 0,6.5" : "-9,-10 9,-10 0,13"} 
                fill="#0E1422" 
                stroke="#00E5FF" 
                strokeWidth={isTactical ? 1 : 2} 
              />
              <line x1="0" y1={isTactical ? -5 : -10} x2="0" y2={isTactical ? -9 : -18} stroke="#00E5FF" strokeWidth={isTactical ? 0.7 : 1.5} />
            </g>

          </g>
        </svg>

        {/* Legend Overlay */}
        <div className="absolute bottom-3 left-3 bg-[#0E1422]/90 border border-[#2A3754] rounded p-2 text-[9px] font-mono space-y-1.5 backdrop-blur-sm">
          <div className="flex items-center space-x-2">
            <span className="w-3 h-0.5 bg-[#10F293]"></span>
            <span className="text-slate-400">Trajectory path</span>
          </div>
          <div className="flex items-center space-x-2">
            <span className="w-3 h-0.5 border-t border-dashed border-[#00E5FF]"></span>
            <span className="text-slate-400">Direct heading intent</span>
          </div>
          <div className="flex items-center space-x-2">
            <span className="w-3 h-3 rounded-full border border-[#FF3366] bg-red-950/10"></span>
            <span className="text-slate-400">Threat boundary</span>
          </div>
        </div>
      </div>
    </div>
  );
}
