import React from 'react';
import { motion } from 'framer-motion';
import type { Route } from '../types';
import { Clock, MapPin, Gauge, Zap, Leaf, Scale } from 'lucide-react';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: (string | undefined | null | false)[]) {
  return twMerge(clsx(inputs));
}

interface RouteCardProps {
  route: Route;
  isSelected: boolean;
  onSelect: (route: Route) => void;
}

export const RouteCard: React.FC<RouteCardProps> = ({ route, isSelected, onSelect }) => {
  const isFast = route.name.toLowerCase().includes('fast');
  const isEasy = route.name.toLowerCase().includes('easy');

  return (
    <motion.div
      whileHover={{ y: -4, scale: 1.01 }}
      whileTap={{ scale: 0.98 }}
      onClick={() => onSelect(route)}
      className={cn(
        "cursor-pointer p-4 rounded-2xl border-2 transition-all duration-300 relative overflow-hidden flex flex-col h-full",
        isSelected 
          ? "border-primary bg-blue-50/30 shadow-lg" 
          : "border-slate-200 bg-slate-50 hover:bg-white hover:border-slate-300 shadow-sm hover:shadow-md"
      )}
    >
      {isSelected && (
        <div className="absolute top-0 right-0 w-24 h-24 bg-gradient-to-bl from-primary/10 to-transparent pointer-events-none rounded-bl-full" />
      )}
      
      <div className="flex items-start justify-between mb-2 mt-0">
        <h3 className="font-extrabold text-lg text-slate-800 flex items-center gap-2">
          {isFast ? <Zap size={20} className="text-rose-500" /> : isEasy ? <Leaf size={20} className="text-emerald-500" /> : <Scale size={20} className="text-blue-500" />}
          {route.name}
        </h3>
        <span className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-100 shadow-sm rounded-full text-sm font-bold text-slate-700">
          <Clock size={14} className="text-primary" /> {route.stats.travel_time_min} min
        </span>
      </div>
      
      <div className="text-slate-500 text-[13px] font-medium leading-relaxed flex-1">{route.description}</div>
      
      <div className="grid grid-cols-2 gap-2 mt-2 pt-2 border-t border-slate-200/60 text-sm font-medium">
        <div className="flex items-center gap-2 text-slate-600 bg-white p-2 rounded-lg border border-slate-100">
          <MapPin size={16} className="text-emerald-500" />
          <span>{route.stats.distance_km} km</span>
        </div>
        <div className="flex items-center gap-2 text-slate-600 bg-white p-2 rounded-lg border border-slate-100">
          <Gauge size={16} className="text-orange-500" />
          <span>Stress: {route.profile.avg_road_stress?.toFixed(1) || '?'}</span>
        </div>
      </div>
    </motion.div>
  );
};
