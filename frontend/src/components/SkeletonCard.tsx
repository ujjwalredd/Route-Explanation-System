import { motion } from 'framer-motion';

export const SkeletonCard = () => {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95, transition: { duration: 0.2 } }}
      className="p-5 rounded-2xl border-2 border-slate-100 bg-white/50 shadow-sm flex flex-col h-full relative overflow-hidden"
    >
      <div className="absolute inset-0 -translate-x-full animate-[shimmer_2s_infinite] bg-gradient-to-r from-transparent via-slate-100/40 to-transparent" />
      
      <div className="flex items-start justify-between mb-4 mt-1">
        <div className="h-6 w-32 bg-slate-200 rounded-lg animate-pulse" />
        <div className="h-6 w-16 bg-slate-200 rounded-full animate-pulse" />
      </div>
      
      <div className="space-y-2 flex-1 mt-2">
        <div className="h-3 w-full bg-slate-100 rounded animate-pulse" />
        <div className="h-3 w-4/5 bg-slate-100 rounded animate-pulse" />
        <div className="h-3 w-5/6 bg-slate-100 rounded animate-pulse" />
      </div>
      
      <div className="grid grid-cols-2 gap-3 mt-5 pt-4 border-t border-slate-100">
        <div className="h-9 w-full bg-slate-100 rounded-lg animate-pulse" />
        <div className="h-9 w-full bg-slate-100 rounded-lg animate-pulse" />
      </div>
    </motion.div>
  );
};
