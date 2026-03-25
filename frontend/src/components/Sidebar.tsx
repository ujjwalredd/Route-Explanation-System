import React from 'react';
import type { Landmark } from '../types';
import { Search, MapPin, Target, Sparkles, Navigation2 } from 'lucide-react';
import { motion } from 'framer-motion';

interface SidebarProps {
  landmarks: Landmark[];
  originName: string;
  destName: string;
  setOriginName: (name: string) => void;
  setDestName: (name: string) => void;
  onSearch: () => void;
  isLoading: boolean;
  summary: any;
}

export const Sidebar: React.FC<SidebarProps> = ({
  landmarks, originName, destName, setOriginName, setDestName, onSearch, isLoading, summary
}) => {
  const SidebarContent = (
    <>
      <div className="p-8 border-b border-slate-100/80 hidden md:block">
        <h1 className="text-2xl font-black text-black tracking-tight leading-tight">
          Route Explanation System
        </h1>
        <p className="text-[10px] text-slate-400 font-bold mt-3 uppercase tracking-widest">Navigation Intelligence</p>
      </div>

      <div className="p-6 md:p-8 flex-1 overflow-y-auto custom-scrollbar">
        <div className="space-y-6">
          <div className="relative group">
            <div className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 rounded-full border-[3px] border-emerald-500 bg-white z-10" />
            <select
              className="w-full pl-12 pr-4 py-4 bg-slate-50 border-2 border-slate-100 rounded-2xl appearance-none focus:outline-none focus:border-emerald-500 focus:bg-white transition-all font-semibold text-slate-700 cursor-pointer shadow-sm hover:border-slate-300"
              value={originName}
              onChange={e => setOriginName(e.target.value)}
            >
              <option value="" disabled className="text-slate-400 font-medium">Where are you?</option>
              {landmarks.map(l => (
                <option key={l.name} value={l.name} className="font-medium text-slate-700 pb-2">{l.name}</option>
              ))}
            </select>
          </div>

          <div className="relative group">
            <div className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 rounded-full border-[3px] border-rose-500 bg-white z-10" />
            <div className="absolute left-[22px] -top-[28px] h-6 w-[2px] border-l-2 border-dashed border-slate-300 z-0" />
            <select
              className="w-full pl-12 pr-4 py-4 bg-slate-50 border-2 border-slate-100 rounded-2xl appearance-none focus:outline-none focus:border-rose-500 focus:bg-white transition-all font-semibold text-slate-700 cursor-pointer shadow-sm hover:border-slate-300"
              value={destName}
              onChange={e => setDestName(e.target.value)}
            >
              <option value="" disabled className="text-slate-400 font-medium">Where to?</option>
              {landmarks.map(l => (
                <option key={l.name} value={l.name} className="font-medium text-slate-700 pb-2">{l.name}</option>
              ))}
            </select>
          </div>

          <button
            onClick={onSearch}
            disabled={isLoading || !originName || !destName}
            className="w-full mt-4 bg-slate-900 hover:bg-black text-white py-4 px-6 rounded-2xl font-bold flex items-center justify-center gap-2 transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-slate-900/20 active:scale-[0.98]"
          >
            {isLoading ? (
              <span className="animate-pulse">Analyzing Topography...</span>
            ) : (
              <>
                <Search size={18} strokeWidth={3} />
                <span>Search Routes</span>
              </>
            )}
          </button>
        </div>

        {summary && (
          <div className="mt-8 bg-slate-50 border-2 border-slate-100 p-5 rounded-2xl shadow-sm">
             <div className="flex items-center gap-2 mb-4 pb-3 border-b border-slate-200/60">
               <Navigation2 size={16} className="text-primary" />
               <span className="text-xs font-bold text-slate-500 uppercase tracking-widest">Global Insights</span>
             </div>
             <p className="text-sm font-semibold text-slate-700 leading-snug">
               Analyzed <strong className="text-primary text-base">{summary.total_cases}</strong> past navigations
             </p>
          </div>
        )}
      </div>
    </>
  );

  return (
    <>
      <motion.div 
        drag="y"
        dragConstraints={{ top: 0, bottom: 400 }}
        dragElastic={0.1}
        className="md:hidden fixed bottom-0 left-0 w-full bg-white/95 backdrop-blur-xl border-t border-slate-200 rounded-t-[2.5rem] shadow-[0_-10px_50px_rgba(0,0,0,0.15)] flex flex-col z-50 pointer-events-auto max-h-[85vh] h-[70vh]"
      >
        <div className="w-full h-10 flex items-center justify-center cursor-grab active:cursor-grabbing shrink-0 mt-2">
           <div className="w-16 h-1.5 bg-slate-300 rounded-full" />
        </div>
        {SidebarContent}
      </motion.div>

      <div className="hidden md:flex w-[380px] bg-white border-r border-slate-200 h-screen flex-col shadow-2xl flex-shrink-0 z-20 relative">
        {SidebarContent}
      </div>
    </>
  );
};
