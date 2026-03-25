import React, { useState, useEffect } from 'react';
import type { Route, Landmark } from './types';
import { Sidebar } from './components/Sidebar';
import { MapComponent as Map } from './components/Map';
import { RouteCard } from './components/RouteCard';
import { Explanation } from './components/Explanation';
import { SkeletonCard } from './components/SkeletonCard';
import { api } from './api';
import { AnimatePresence, motion } from 'framer-motion';

const App = () => {
  const [selectedRoute, setSelectedRoute] = useState<Route | null>(null);
  
  const [originName, setOriginName] = useState('');
  const [destName, setDestName] = useState('');
  
  const [isLoading, setIsLoading] = useState(false);
  const [routes, setRoutes] = useState<Route[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const [landmarks, setLandmarks] = useState<Landmark[]>([]);
  
  const [explanation, setExplanation] = useState<string>('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [feedbackGiven, setFeedbackGiven] = useState(false);

  const [focusedTurnCoord, setFocusedTurnCoord] = useState<[number, number] | null>(null);

  useEffect(() => {
    api.getLandmarks().then((res: any) => setLandmarks(res));
    api.getCasesSummary().then((res: any) => setSummary(res));
  }, []);

  const handleSearch = async () => {
    setIsLoading(true);
    setRoutes([]);
    setSelectedRoute(null);
    setExplanation('');
    setFeedbackGiven(false);
    setFocusedTurnCoord(null);
    
    try {
      const res = await api.getRoutes({ origin_name: originName, dest_name: destName });
      setRoutes(res.routes);
      if (res.routes.length > 0) {
        handleSelectRoute(res.routes[0], res.routes);
      }
    } catch (e) {
      console.error("Error fetching routes:", e);
      alert("Error generating routes. Is the backend running?");
    } finally {
      setIsLoading(false);
    }
  };

  const handleSelectRoute = async (route: Route, allRoutesVar = routes) => {
    setSelectedRoute(route);
    setExplanation('');
    setFeedbackGiven(false);
    setFocusedTurnCoord(null);
    
    setIsStreaming(true);
    try {
      const payloadRoute = { ...route, coords: [] };
      const payloadAllRoutes = allRoutesVar.map(r => ({ ...r, coords: [] }));
      const response = await fetch('http://localhost:8000/api/explain', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chosen_route: payloadRoute, all_routes: payloadAllRoutes, use_llm: true })
      });
      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      if (reader) {
        let done = false;
        let text = '';
        while (!done) {
          const { value, done: doneReading } = await reader.read();
          done = doneReading;
          const chunk = decoder.decode(value, { stream: true });
          text += chunk;
          setExplanation(text);
        }
      }
    } catch (e) {
      console.error(e);
    } finally {
      setIsStreaming(false);
    }
  };

  const handleFeedback = async (score: number) => {
    if (!selectedRoute) return;
    try {
      await api.submitFeedback({
        origin_name: originName,
        dest_name: destName,
        chosen_route: { ...selectedRoute, coords: [] },
        feedback_score: score
      });
      setFeedbackGiven(true);
      const res = await api.getCasesSummary();
      setSummary(res);
    } catch (e) {
      console.error("Feedback error", e);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex font-sans overflow-hidden">
      <div className="fixed inset-0 z-0 bg-slate-100/50" />
      
      <Sidebar 
        landmarks={landmarks}
        originName={originName}
        destName={destName}
        setOriginName={setOriginName}
        setDestName={setDestName}
        onSearch={handleSearch}
        isLoading={isLoading}
        summary={summary}
      />

      <div className="flex-1 p-2 md:p-6 flex flex-col h-[65vh] md:h-screen overflow-hidden relative z-10 w-full mb-[35vh] md:mb-0">
        <div className="w-full flex flex-col h-full gap-4 md:gap-6">
          <div className="flex-1 relative z-0 min-h-0">
            <Map 
              routes={routes} 
              selectedRouteName={selectedRoute?.name} 
              origin={landmarks.find(l => l.name === originName)}
              dest={landmarks.find(l => l.name === destName)}
              focusedTurnCoord={focusedTurnCoord}
            />
          </div>

          <AnimatePresence>
            {(routes.length > 0 || isLoading) && (
              <motion.div 
                initial={{ opacity: 0, y: 50 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 50 }}
                className="grid grid-cols-1 lg:grid-cols-2 gap-4 lg:gap-6 shrink-0 z-10 lg:h-[340px] xl:h-[360px] overflow-visible pb-[20vh] md:pb-0"
              >
                <div className="flex flex-col h-[280px] lg:h-full bg-white shadow-xl shadow-slate-200/50 border border-slate-200 rounded-2xl p-5 lg:p-6 overflow-hidden min-h-0">
                  <h3 className="text-[11px] font-extrabold text-slate-400 uppercase tracking-widest mb-3 lg:mb-4 px-1 shrink-0">Proposed Routes</h3>
                  <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4 lg:gap-5 overflow-y-auto custom-scrollbar pr-2 md:pr-0 flex-1 pb-2 auto-rows-fr">
                    {isLoading ? (
                      <>
                        {[1, 2, 3].map((i, idx) => (
                          <motion.div
                            key={`skeleton-${i}`}
                            initial={{ opacity: 0, y: 30 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, scale: 0.95 }}
                            transition={{ delay: idx * 0.12, type: 'spring' }}
                            className="h-full"
                          >
                            <SkeletonCard />
                          </motion.div>
                        ))}
                      </>
                    ) : (
                      <AnimatePresence>
                        {routes.map((route, idx) => (
                          <motion.div 
                            key={`route-${route.name}`}
                            initial={{ opacity: 0, scale: 0.9, y: 20 }}
                            animate={{ opacity: 1, scale: 1, y: 0 }}
                            transition={{ delay: idx * 0.1, type: 'spring' }}
                            className="h-full"
                          >
                            <RouteCard 
                              route={route}
                              isSelected={selectedRoute?.name === route.name}
                              onSelect={(r) => handleSelectRoute(r, routes)}
                            />
                          </motion.div>
                        ))}
                      </AnimatePresence>
                    )}
                  </div>
                </div>

                <div className="h-[380px] lg:h-full min-h-0">
                  {!isLoading && selectedRoute && (
                    <Explanation 
                      route={selectedRoute} 
                      explanation={explanation} 
                      isStreaming={isStreaming} 
                      onFeedback={handleFeedback}
                      feedbackGiven={feedbackGiven}
                      onHoverTurn={setFocusedTurnCoord}
                    />
                  )}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
};

export default App;
