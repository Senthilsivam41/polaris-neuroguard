import { useState } from 'react';
import { FilePenLine, Loader2, CheckCircle2, XCircle } from 'lucide-react';
import { useSimulationStore } from '../../store/useSimulationStore';

export default function AmendmentPanel() {
  const store = useSimulationStore();
  const [draft, setDraft] = useState('Add observability dashboards to the migration.');
  const [rationale, setRationale] = useState('Product accepts scoped extension.');

  if (store.currentSimulationId === 'Not Initialized') {
    return null;
  }

  const findings = store.amendmentEvaluation?.deterministic_findings || [];

  return (
    <div className="mt-4 space-y-3 border-t border-[#2A3754]/50 pt-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <FilePenLine className="w-4 h-4 text-accent-cyan" />
          <h3 className="font-semibold text-xs tracking-wider text-slate-200 uppercase">
            Goal Contract Amendment
          </h3>
        </div>
        <span className="text-[10px] font-mono text-slate-500">
          v{store.activeContractVersion}
        </span>
      </div>

      <textarea
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        rows={3}
        className="w-full bg-[#0E1422] border border-[#2A3754] rounded p-2 text-[11px] text-slate-100 font-mono focus:border-accent-cyan focus:outline-none"
        placeholder="Natural-language change request…"
      />

      <button
        type="button"
        disabled={store.isAmending || !draft.trim()}
        onClick={() => store.submitAmendmentDraft(draft.trim())}
        className="w-full bg-[#0E1422] hover:bg-[#1C253B] disabled:opacity-50 border border-accent-cyan/30 text-accent-cyan font-mono text-[10px] py-2 rounded flex items-center justify-center space-x-2"
      >
        {store.isAmending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
        <span>SUBMIT & EVALUATE DRIFT</span>
      </button>

      {store.amendmentEvaluation && (
        <div className="bg-[#0E1422] border border-[#2A3754] rounded p-3 space-y-2 text-[10px] font-mono text-slate-400">
          <p>
            <span className="text-slate-600">ACTION:</span>{' '}
            <span className="text-accent-cyan font-bold">
              {String(store.amendmentEvaluation.recommended_action || store.amendmentEvaluation.classification_status || 'n/a')}
            </span>
          </p>
          {typeof store.amendmentEvaluation.semantic_score === 'number' && (
            <p>
              <span className="text-slate-600">SEMANTIC SCORE:</span>{' '}
              {store.amendmentEvaluation.semantic_score.toFixed(2)}
            </p>
          )}
          {findings.length > 0 && (
            <div className="space-y-1">
              <p className="text-slate-600">FINDINGS:</p>
              {findings.map((f, i) => (
                <p key={i} className="text-slate-300">
                  • {f.category}{f.evidence ? ` — ${f.evidence}` : ''}
                </p>
              ))}
            </div>
          )}

          <input
            type="text"
            value={rationale}
            onChange={(e) => setRationale(e.target.value)}
            className="w-full bg-slate-950/40 border border-[#2A3754] rounded p-1.5 text-slate-200"
            placeholder="Decision rationale"
          />

          <div className="grid grid-cols-2 gap-2 pt-1">
            <button
              type="button"
              disabled={store.isAmending}
              onClick={() => store.decideAmendment('APPROVE', rationale)}
              className="flex items-center justify-center space-x-1 py-1.5 rounded border border-emerald-500/40 text-emerald-400 hover:bg-emerald-950/30"
            >
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>APPROVE</span>
            </button>
            <button
              type="button"
              disabled={store.isAmending}
              onClick={() => store.decideAmendment('REJECT', rationale)}
              className="flex items-center justify-center space-x-1 py-1.5 rounded border border-alert-crimson/40 text-alert-crimson hover:bg-red-950/30"
            >
              <XCircle className="w-3.5 h-3.5" />
              <span>REJECT</span>
            </button>
          </div>
        </div>
      )}

      {store.amendmentMessage && (
        <p className="text-[10px] font-mono text-slate-500">{store.amendmentMessage}</p>
      )}
    </div>
  );
}
