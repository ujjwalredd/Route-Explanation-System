import React from 'react';
import type { Route } from '../types';
import { ThumbsUp, ThumbsDown } from 'lucide-react';

interface ExplanationProps {
  route: Route;
  explanation: string;
  isStreaming: boolean;
  onFeedback: (score: number) => void;
  feedbackGiven: boolean;
  onHoverTurn?: (coord: [number, number] | null) => void;
}

export const Explanation: React.FC<ExplanationProps> = ({ route, explanation, isStreaming, onFeedback, feedbackGiven, onHoverTurn }) => {

  const normalize = (text: string) => {
    const escaped = text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');

    let html = escaped;
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
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
        const worstEdge = difficultEdges.reduce((prev, current) => (prev.turn_difficulty > current.turn_difficulty) ? prev : current);
        if (worstEdge.turn_coord) {
          onHoverTurn(worstEdge.turn_coord);
        }
      }
    }
  };

  const handleMouseOut = (e: React.MouseEvent) => {
    const target = e.target as HTMLElement;
    if (target.classList.contains('turn-scrub-trigger') && onHoverTurn) {
      onHoverTurn(null);
    }
  };

  const scrollRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (isStreaming && scrollRef.current) {
        scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [explanation, isStreaming]);

  return (
    <div className="bg-white rounded-2xl border-2 border-slate-200 shadow-xl shadow-slate-200/50 p-6 flex flex-col h-full overflow-hidden min-h-0 shrink-0">
      <h2 className="text-xl font-extrabold text-slate-900 mb-4 pb-4 border-b border-slate-100 flex items-center gap-2 shrink-0">
        Explanation: {route.name}
      </h2>
      
      <div 
        ref={scrollRef}
        className="flex-1 overflow-y-auto pr-3 custom-scrollbar text-sm min-h-0"
        onMouseOver={handleMouseOver}
        onMouseOut={handleMouseOut}
      >
        <div className="prose prose-sm prose-slate max-w-none text-slate-600 leading-relaxed explanation-content" dangerouslySetInnerHTML={{ __html: html }} />
        {isStreaming && (
          <div className="mt-4 flex items-center gap-2 text-primary text-xs font-bold animate-pulse">
            <div className="w-1.5 h-1.5 bg-primary rounded-full" />
            Generating explanation...
          </div>
        )}
      </div>

      <div className="mt-4 pt-4 border-t border-slate-100 flex items-center justify-between shrink-0">
        <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">Route feedback</span>
        <div className="flex items-center gap-2">
          {feedbackGiven ? (
            <span className="text-sm font-semibold text-emerald-500 bg-emerald-50 px-3 py-1.5 rounded-full border border-emerald-100">Thanks for your feedback!</span>
          ) : (
            <>
              <button onClick={() => onFeedback(5)} disabled={isStreaming} className="p-2 hover:bg-emerald-50 hover:text-emerald-600 rounded-full text-slate-400 transition-colors disabled:opacity-50 border border-transparent hover:border-emerald-100">
                <ThumbsUp size={18} />
              </button>
              <button onClick={() => onFeedback(1)} disabled={isStreaming} className="p-2 hover:bg-rose-50 hover:text-rose-600 rounded-full text-slate-400 transition-colors disabled:opacity-50 border border-transparent hover:border-rose-100">
                <ThumbsDown size={18} />
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
