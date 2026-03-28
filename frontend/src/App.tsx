import { useState, useEffect } from 'react';
import type { Route, Landmark, ArgueData } from './types';
import { Sidebar } from './components/Sidebar';
import { MapComponent as Map } from './components/Map';
import { RouteCard } from './components/RouteCard';
import { Explanation } from './components/Explanation';
import { SkeletonCard } from './components/SkeletonCard';
import { api } from './api';
import { AnimatePresence, motion } from 'framer-motion';

// Generate or retrieve a persistent participant ID for study mode
function getParticipantId(): string {
  const key = 'res_participant_id';
  let id = localStorage.getItem(key);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(key, id);
  }
  return id;
}

const App = () => {
  const [selectedRoute, setSelectedRoute] = useState<Route | null>(null);

  const [originName, setOriginName] = useState('');
  const [destName, setDestName] = useState('');
  const [departureHour, setDepartureHour] = useState('');
  const [activeMode, setActiveMode] = useState('argumentation');

  const [isLoading, setIsLoading] = useState(false);
  const [routes, setRoutes] = useState<Route[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const [landmarks, setLandmarks] = useState<Landmark[]>([]);

  const [explanation, setExplanation] = useState<string>('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [feedbackGiven, setFeedbackGiven] = useState(false);
  const [argueData, setArgueData] = useState<ArgueData | null>(null);

  const [focusedTurnCoord, setFocusedTurnCoord] = useState<[number, number] | null>(null);

  // Study mode state
  const isStudyMode = new URLSearchParams(window.location.search).get('study') === 'true';
  const [showStudyPanel, setShowStudyPanel] = useState(false);
  const [studyRatings, setStudyRatings] = useState<{ trust: number; clarity: number; safety: number }>({ trust: 0, clarity: 0, safety: 0 });
  const [studySubmitted, setStudySubmitted] = useState(false);

  useEffect(() => {
    api.getLandmarks().then((res: any) => setLandmarks(res));
    api.getCasesSummary().then((res: any) => setSummary(res));
  }, []);

  // Show study panel when streaming ends
  useEffect(() => {
    if (isStudyMode && !isStreaming && selectedRoute && explanation) {
      setShowStudyPanel(true);
      setStudySubmitted(false);
      setStudyRatings({ trust: 0, clarity: 0, safety: 0 });
    }
  }, [isStreaming, isStudyMode, selectedRoute, explanation]);

  const handleSearch = async () => {
    setIsLoading(true);
    setRoutes([]);
    setSelectedRoute(null);
    setExplanation('');
    setFeedbackGiven(false);
    setFocusedTurnCoord(null);
    setShowStudyPanel(false);

    try {
      const res = await api.getRoutes({
        origin_name: originName,
        dest_name: destName,
        departure_hour: departureHour ? parseInt(departureHour) : null,
      });
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

  const handleSelectRoute = async (route: Route, allRoutesVar = routes, modeOverride?: string) => {
    setSelectedRoute(route);
    setExplanation('');
    setArgueData(null);
    setFeedbackGiven(false);
    setFocusedTurnCoord(null);
    setShowStudyPanel(false);

    const mode = modeOverride ?? activeMode;

    setIsStreaming(true);
    try {
      const payloadRoute = { ...route, coords: [] };
      const payloadAllRoutes = allRoutesVar.map(r => ({ ...r, coords: [] }));

      const arguePromise = fetch('http://localhost:8000/api/argue', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chosen_route: payloadRoute, all_routes: payloadAllRoutes })
      }).then(r => r.json()).then(data => setArgueData(data)).catch(() => {});

      const explainPromise = (async () => {
        const response = await fetch('http://localhost:8000/api/explain', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ chosen_route: payloadRoute, all_routes: payloadAllRoutes, use_llm: true, mode })
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
      })();

      await Promise.all([arguePromise, explainPromise]);
    } catch (e) {
      console.error(e);
    } finally {
      setIsStreaming(false);
    }
  };

  const handleModeChange = (mode: string) => {
    setActiveMode(mode);
    if (selectedRoute) {
      handleSelectRoute(selectedRoute, routes, mode);
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

  const handleStudySubmit = async () => {
    if (studyRatings.trust === 0 || studyRatings.clarity === 0 || studyRatings.safety === 0) return;
    try {
      await fetch('http://localhost:8000/api/study/response', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          participant_id: getParticipantId(),
          mode: activeMode,
          route_name: selectedRoute?.name,
          origin: originName,
          destination: destName,
          trust: studyRatings.trust,
          clarity: studyRatings.clarity,
          safety: studyRatings.safety,
        })
      });
    } catch (_) {
      // backend may not have study endpoint yet, fail silently
    }
    setStudySubmitted(true);
    setShowStudyPanel(false);
  };

  const LikertScale = ({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) => (
    <div className="flex items-center gap-3">
      <span className="text-xs font-semibold text-slate-600 w-14">{label}</span>
      <div className="flex gap-1.5">
        {[1, 2, 3, 4, 5].map(n => (
          <button
            key={n}
            onClick={() => onChange(n)}
            className={`w-7 h-7 rounded-full text-xs font-bold border-2 transition-all ${
              value === n
                ? 'bg-indigo-600 border-indigo-600 text-white'
                : 'border-slate-200 text-slate-400 hover:border-indigo-300 hover:text-indigo-500'
            }`}
          >
            {n}
          </button>
        ))}
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-slate-50 flex font-sans overflow-hidden">
      <div className="fixed inset-0 z-0 bg-slate-100/50" />

      {/* Study mode banner */}
      {isStudyMode && (
        <div className="fixed top-0 left-0 right-0 z-50 bg-indigo-600 text-white text-center text-xs font-semibold py-2 px-4 shadow-lg">
          You are participating in a route explanation study. Please evaluate each explanation using the rating form below.
        </div>
      )}

      <Sidebar
        landmarks={landmarks}
        originName={originName}
        destName={destName}
        setOriginName={setOriginName}
        setDestName={setDestName}
        onSearch={handleSearch}
        isLoading={isLoading}
        summary={summary}
        departureHour={departureHour}
        setDepartureHour={setDepartureHour}
      />

      <div className={`flex-1 p-2 md:p-6 flex flex-col h-[65vh] md:h-screen overflow-hidden relative z-10 w-full mb-[35vh] md:mb-0 ${isStudyMode ? 'pt-10 md:pt-12' : ''}`}>
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
                className="grid grid-cols-1 lg:grid-cols-2 gap-4 lg:gap-6 shrink-0 z-10 lg:h-[400px] xl:h-[440px] overflow-visible pb-[20vh] md:pb-0"
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
                      argueData={argueData}
                      activeMode={activeMode}
                      onModeChange={handleModeChange}
                    />
                  )}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* Study mode rating panel */}
      {isStudyMode && showStudyPanel && !studySubmitted && (
        <div className="fixed bottom-0 left-0 right-0 z-50 bg-white border-t-2 border-indigo-200 shadow-2xl px-6 py-4">
          <p className="text-sm font-bold text-slate-700 mb-3">Rate this explanation:</p>
          <div className="flex flex-col gap-2 mb-4">
            <LikertScale label="Trust" value={studyRatings.trust} onChange={v => setStudyRatings(r => ({ ...r, trust: v }))} />
            <LikertScale label="Clarity" value={studyRatings.clarity} onChange={v => setStudyRatings(r => ({ ...r, clarity: v }))} />
            <LikertScale label="Safety" value={studyRatings.safety} onChange={v => setStudyRatings(r => ({ ...r, safety: v }))} />
          </div>
          <button
            onClick={handleStudySubmit}
            disabled={studyRatings.trust === 0 || studyRatings.clarity === 0 || studyRatings.safety === 0}
            className="bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-bold py-2 px-6 rounded-xl disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            Submit Rating
          </button>
        </div>
      )}
    </div>
  );
};

export default App;
