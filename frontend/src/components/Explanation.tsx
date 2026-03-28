import React, { useState } from 'react';
import type { Route, ArgueData } from '../types';
import { ThumbsUp, ThumbsDown, Clock, Wind, CornerDownRight, Lightbulb, GitBranch, ChevronDown, ChevronUp } from 'lucide-react';

interface ExplanationProps {
  route: Route;
  explanation: string;
  isStreaming: boolean;
  onFeedback: (score: number) => void;
  feedbackGiven: boolean;
  onHoverTurn?: (coord: [number, number] | null) => void;
  argueData?: ArgueData | null;
  onModeChange?: (mode: string) => void;
  activeMode?: string;
}

const DIM_ICONS: Record<string, React.ReactNode> = {
  time: <Clock size={11} />,
  stress: <Wind size={11} />,
  turns: <CornerDownRight size={11} />,
};

const DIM_COLORS: Record<string, string> = {
  time: 'bg-amber-50 text-amber-700 border-amber-200',
  stress: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  turns: 'bg-violet-50 text-violet-700 border-violet-200',
};

const DIM_LABELS: Record<string, string> = {
  time: 'Time',
  stress: 'Stress',
  turns: 'Turns',
};

// SVG Argument Graph component
const ArgumentGraph: React.FC<{ argueData: ArgueData }> = ({ argueData }) => {
  const args = argueData.argumentation_framework.arguments;
  const attacks = argueData.argumentation_framework.attacks;

  // Group by route name, then polarity within route
  const routeGroups: Record<string, typeof args> = {};
  for (const arg of args) {
    if (!routeGroups[arg.route]) routeGroups[arg.route] = [];
    routeGroups[arg.route].push(arg);
  }

  const routeNames = Object.keys(routeGroups);
  const numCols = routeNames.length;

  // Layout constants
  const colWidth = 140;
  const rowHeight = 60;
  const nodeR = 14;
  const svgPaddingX = 20;
  const svgPaddingY = 30;

  // Compute positions for each node
  const positions: Record<string, { x: number; y: number }> = {};
  const dimOrder = ['time', 'stress', 'turns', 'cbr'];

  for (let ci = 0; ci < routeNames.length; ci++) {
    const rName = routeNames[ci];
    const group = routeGroups[rName];
    // Sort by dimension then polarity (pro on top, con below)
    const sorted = [...group].sort((a, b) => {
      const di = dimOrder.indexOf(a.dimension) - dimOrder.indexOf(b.dimension);
      if (di !== 0) return di;
      // pro before con
      return a.polarity === 'pro' ? -1 : 1;
    });
    // Each dim: pro at even row, con at odd row (offset within col)
    for (let ri = 0; ri < sorted.length; ri++) {
      const x = svgPaddingX + ci * colWidth + colWidth / 2;
      const y = svgPaddingY + ri * rowHeight + nodeR;
      positions[sorted[ri].id] = { x, y };
    }
  }

  const maxRows = Math.max(...routeNames.map(rn => routeGroups[rn].length));
  const svgWidth = svgPaddingX * 2 + numCols * colWidth;
  const svgHeight = svgPaddingY + maxRows * rowHeight + nodeR + 20;

  const statusColor = (status: string) => {
    if (status === 'IN') return '#22c55e';
    if (status === 'OUT') return '#ef4444';
    return '#94a3b8';
  };

  // Arrow marker
  const markerId = 'arrowhead';
  const markerIdDashed = 'arrowhead-dashed';

  // Compute line endpoints that stop at node edge
  const lineEndpoints = (fromId: string, toId: string) => {
    const from = positions[fromId];
    const to = positions[toId];
    if (!from || !to) return null;
    const dx = to.x - from.x;
    const dy = to.y - from.y;
    const dist = Math.sqrt(dx * dx + dy * dy);
    if (dist === 0) return null;
    const ux = dx / dist;
    const uy = dy / dist;
    return {
      x1: from.x + ux * nodeR,
      y1: from.y + uy * nodeR,
      x2: to.x - ux * (nodeR + 4),
      y2: to.y - uy * (nodeR + 4),
    };
  };

  return (
    <div className="w-full overflow-x-auto">
      <svg
        width="100%"
        viewBox={`0 0 ${svgWidth} ${svgHeight}`}
        style={{ maxHeight: 200, display: 'block' }}
      >
        <defs>
          <marker id={markerId} markerWidth="8" markerHeight="8" refX="4" refY="2" orient="auto">
            <path d="M0,0 L0,4 L6,2 z" fill="#64748b" />
          </marker>
          <marker id={markerIdDashed} markerWidth="8" markerHeight="8" refX="4" refY="2" orient="auto">
            <path d="M0,0 L0,4 L6,2 z" fill="#cbd5e1" />
          </marker>
        </defs>

        {/* Column route labels */}
        {routeNames.map((rn, ci) => (
          <text
            key={rn}
            x={svgPaddingX + ci * colWidth + colWidth / 2}
            y={14}
            textAnchor="middle"
            fontSize={9}
            fontWeight="bold"
            fill="#64748b"
          >
            {rn.length > 14 ? rn.slice(0, 12) + '…' : rn}
          </text>
        ))}

        {/* Attack lines */}
        {attacks.map((atk, i) => {
          const ep = lineEndpoints(atk.attacker_id, atk.target_id);
          if (!ep) return null;
          return (
            <line
              key={i}
              x1={ep.x1} y1={ep.y1} x2={ep.x2} y2={ep.y2}
              stroke={atk.succeeds ? '#64748b' : '#cbd5e1'}
              strokeWidth={atk.succeeds ? 1.5 : 1}
              strokeDasharray={atk.succeeds ? undefined : '4,3'}
              markerEnd={`url(#${atk.succeeds ? markerId : markerIdDashed})`}
            />
          );
        })}

        {/* Nodes */}
        {args.map(arg => {
          const pos = positions[arg.id];
          if (!pos) return null;
          const fill = statusColor(arg.status);
          const label = `${arg.dimension}:${arg.polarity === 'pro' ? '+' : '-'}`;
          return (
            <g key={arg.id}>
              <circle cx={pos.x} cy={pos.y} r={nodeR} fill={fill} fillOpacity={0.2} stroke={fill} strokeWidth={2} />
              <text x={pos.x} y={pos.y + 3.5} textAnchor="middle" fontSize={7} fontWeight="bold" fill={fill}>
                {label.length > 8 ? label.slice(0, 7) : label}
              </text>
            </g>
          );
        })}
      </svg>

      {/* Legend */}
      <div className="flex items-center gap-3 mt-1 px-1">
        {[['#22c55e', 'Accepted'], ['#ef4444', 'Rejected'], ['#94a3b8', 'Undecided']].map(([color, label]) => (
          <div key={label} className="flex items-center gap-1">
            <div className="w-2.5 h-2.5 rounded-full border-2" style={{ borderColor: color, backgroundColor: color + '33' }} />
            <span className="text-[10px] text-slate-500">{label}</span>
          </div>
        ))}
        <div className="flex items-center gap-1 ml-1">
          <svg width="20" height="8">
            <line x1="0" y1="4" x2="14" y2="4" stroke="#64748b" strokeWidth="1.5" markerEnd="url(#arrowhead)" />
          </svg>
          <span className="text-[10px] text-slate-500">defeats</span>
        </div>
        <div className="flex items-center gap-1">
          <svg width="20" height="8">
            <line x1="0" y1="4" x2="14" y2="4" stroke="#cbd5e1" strokeWidth="1" strokeDasharray="3,2" markerEnd="url(#arrowhead-dashed)" />
          </svg>
          <span className="text-[10px] text-slate-500">fails</span>
        </div>
      </div>
    </div>
  );
};

export const Explanation: React.FC<ExplanationProps> = ({
  route,
  explanation,
  isStreaming,
  onFeedback,
  feedbackGiven,
  onHoverTurn,
  argueData,
  onModeChange,
  activeMode = 'argumentation',
}) => {
  const [showGraph, setShowGraph] = useState(false);

  const normalize = (text: string) => {
    const escaped = text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');

    let html = escaped;
    html = html.replace(/~~(.*?)~~/g, '<s class="line-through text-slate-400">$1</s>');
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
    html = html.replace(/_(.*?)_/g, '<em>$1</em>');
    html = html.replace(/^\s*-\s+(.*)$/gm, '<div class="pl-3">• $1</div>');
    html = html.replace(/Turn Complexity/gi, '<span class="turn-scrub-trigger font-extrabold text-rose-500 border-b-2 border-rose-500/30 cursor-crosshair transition-all hover:bg-rose-500/10 px-1 rounded">Turn Complexity</span>');
    html = html.replace(/\n{2,}/g, '<br/><br/>').replace(/\n/g, '<br/>');
    return html;
  };

  const html = normalize(explanation || '');

  const handleMouseOver = (e: React.MouseEvent) => {
    const target = e.target as HTMLElement;
    if (target.classList.contains('turn-scrub-trigger') && onHoverTurn) {
      const difficultEdges = route.edges?.filter(edge => edge.turn_difficulty >= 1.0) || [];
      if (difficultEdges.length > 0) {
        const worstEdge = difficultEdges.reduce((prev, current) =>
          prev.turn_difficulty > current.turn_difficulty ? prev : current
        );
        if (worstEdge.turn_coord) onHoverTurn(worstEdge.turn_coord);
      }
    }
  };

  const handleMouseOut = (e: React.MouseEvent) => {
    const target = e.target as HTMLElement;
    if (target.classList.contains('turn-scrub-trigger') && onHoverTurn) onHoverTurn(null);
  };

  const scrollRef = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => {
    if (isStreaming && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [explanation, isStreaming]);

  const verdict: string | null = argueData?.verdict ?? null;
  const counterfactual: string | null = argueData?.counterfactual ?? null;
  const decisiveness: number | null = argueData?.decisiveness ?? null;
  const dimWinners: Record<string, string> = argueData?.dimension_winners ?? {};

  const routeWins = Object.entries(dimWinners)
    .filter(([, winnerName]) => winnerName === route.name)
    .map(([dim]) => dim);

  const MODES = [
    { id: 'argumentation', label: 'Argumentation' },
    { id: 'template', label: 'Template' },
    { id: 'llm', label: 'LLM' },
  ] as const;

  // Route color tint for active tab
  const routeColorHex = route.color ?? '#6366f1';

  return (
    <div className="bg-white rounded-2xl border-2 border-slate-200 shadow-xl shadow-slate-200/50 p-4 flex flex-col h-full overflow-hidden min-h-0 shrink-0">
      {/* Header row: title + mode tabs */}
      <div className="shrink-0 flex items-center justify-between mb-1.5">
        <h2 className="text-sm font-extrabold text-slate-900 truncate mr-2">
          {route.name}
        </h2>
        <div className="flex items-center gap-0.5 bg-slate-100 rounded-lg p-0.5 shrink-0">
          {MODES.map(m => (
            <button
              key={m.id}
              onClick={() => onModeChange?.(m.id)}
              className="text-[10px] font-bold px-2 py-0.5 rounded-md transition-all"
              style={
                activeMode === m.id
                  ? { backgroundColor: routeColorHex + '22', color: routeColorHex, border: `1px solid ${routeColorHex}44` }
                  : { color: '#94a3b8' }
              }
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>

      {/* Verdict */}
      {verdict && (
        <p className="text-[11px] text-slate-600 leading-snug mb-1.5 shrink-0">{verdict}</p>
      )}

      {/* Chips + decisiveness — single compact row */}
      {(routeWins.length > 0 || decisiveness !== null) && (
        <div className="flex flex-wrap items-center gap-1.5 mb-2 shrink-0">
          {routeWins.map(dim => (
            <span
              key={dim}
              className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full text-[10px] font-bold border ${DIM_COLORS[dim] ?? 'bg-slate-50 text-slate-600 border-slate-200'}`}
            >
              {DIM_ICONS[dim]}
              {DIM_LABELS[dim] ?? dim}
            </span>
          ))}
          {decisiveness !== null && (
            <div className="flex items-center gap-1 ml-auto">
              <span className="text-[10px] text-slate-400 font-semibold">Confidence</span>
              <div className="w-16 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-indigo-400 to-indigo-600"
                  style={{ width: `${Math.round(decisiveness * 100)}%` }}
                />
              </div>
              <span className="text-[10px] font-bold text-indigo-600">{Math.round(decisiveness * 100)}%</span>
            </div>
          )}
        </div>
      )}

      <div className="border-t border-slate-100 mb-2 shrink-0" />

      {/* D. Argument Graph SVG */}
      {argueData && activeMode === 'argumentation' && (
        <div className="shrink-0 mb-2">
          <button
            onClick={() => setShowGraph(g => !g)}
            className="flex items-center gap-1 text-[11px] font-bold text-slate-400 hover:text-slate-600 transition-colors mb-1"
          >
            <GitBranch size={11} />
            {showGraph ? 'Hide' : 'Show'} argument graph
            {showGraph ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
          </button>
          {showGraph && (
            <div className="border border-slate-100 rounded-xl bg-slate-50/50 px-2 py-1.5 overflow-hidden">
              <ArgumentGraph argueData={argueData} />
            </div>
          )}
        </div>
      )}

      {/* E. Scrollable explanation text */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto pr-2 custom-scrollbar text-sm min-h-0"
        onMouseOver={handleMouseOver}
        onMouseOut={handleMouseOut}
      >
        <div
          className="prose prose-sm prose-slate max-w-none text-slate-600 leading-relaxed explanation-content"
          dangerouslySetInnerHTML={{ __html: html }}
        />
        {isStreaming && (
          <div className="mt-3 flex items-center gap-2 text-primary text-xs font-bold animate-pulse">
            <div className="w-1.5 h-1.5 bg-primary rounded-full" />
            Generating explanation...
          </div>
        )}
      </div>

      {/* F. Counterfactual */}
      {counterfactual && !isStreaming && (
        <div className="mt-2 shrink-0 bg-amber-50 border border-amber-200 rounded-lg px-2.5 py-1.5 flex gap-1.5 items-start">
          <Lightbulb size={13} className="text-amber-500 mt-0.5 shrink-0" />
          <p className="text-[12px] text-amber-800 leading-snug">{counterfactual}</p>
        </div>
      )}

      {/* Faithfulness + semantics badges — single row */}
      {(argueData?.faithfulness || argueData?.semantics_comparison) && (
        <div className="mt-1.5 mb-0.5 shrink-0 flex items-center gap-2 flex-wrap">
          {argueData?.faithfulness && (
            <span className={`inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full border ${argueData.faithfulness.score >= 1.0 ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-amber-50 text-amber-700 border-amber-200'}`}>
              Faith {argueData.faithfulness.total_checked - argueData.faithfulness.violations}/{argueData.faithfulness.total_checked} {argueData.faithfulness.score >= 1.0 ? '✓' : '⚠'}
            </span>
          )}
          {argueData?.semantics_comparison && (
            <span className={`inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full border ${argueData.semantics_comparison.all_semantics_agree ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-amber-50 text-amber-700 border-amber-200'}`}>
              {argueData.semantics_comparison.all_semantics_agree ? '3 semantics agree ✓' : 'Semantics diverge'}
            </span>
          )}
        </div>
      )}

      {/* Feedback */}
      <div className="mt-2 pt-2 border-t border-slate-100 flex items-center justify-between shrink-0">
        <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">Route feedback</span>
        <div className="flex items-center gap-2">
          {feedbackGiven ? (
            <span className="text-sm font-semibold text-emerald-500 bg-emerald-50 px-3 py-1.5 rounded-full border border-emerald-100">
              Thanks for your feedback!
            </span>
          ) : (
            <>
              <button
                onClick={() => onFeedback(5)}
                disabled={isStreaming}
                className="p-2 hover:bg-emerald-50 hover:text-emerald-600 rounded-full text-slate-400 transition-colors disabled:opacity-50 border border-transparent hover:border-emerald-100"
              >
                <ThumbsUp size={18} />
              </button>
              <button
                onClick={() => onFeedback(1)}
                disabled={isStreaming}
                className="p-2 hover:bg-rose-50 hover:text-rose-600 rounded-full text-slate-400 transition-colors disabled:opacity-50 border border-transparent hover:border-rose-100"
              >
                <ThumbsDown size={18} />
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
