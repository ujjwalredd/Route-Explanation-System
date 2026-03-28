import React, { useEffect, useRef, useState } from 'react';
import Map, { Source, Layer, Marker } from 'react-map-gl/maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';
import type { Route, Landmark } from '../types';

interface MapProps {
  routes: Route[];
  selectedRouteName?: string;
  origin?: Landmark;
  dest?: Landmark;
  focusedTurnCoord?: [number, number] | null;
}

export const MapComponent: React.FC<MapProps> = ({ routes, selectedRouteName, origin, dest, focusedTurnCoord }) => {
  const mapRef = useRef<any>(null);
  const [routeReveal, setRouteReveal] = useState<Record<string, number>>({});
  const animRef = useRef<number>(0);

  useEffect(() => {
    cancelAnimationFrame(animRef.current);
    if (routes.length === 0) { setRouteReveal({}); return; }

    const startTime = performance.now();
    const DURATION = 1000;
    const STAGGER = 160;

    const step = (now: number) => {
      const elapsed = now - startTime;
      const reveal: Record<string, number> = {};
      let allDone = true;
      routes.forEach((route, i) => {
        const t = Math.min(Math.max((elapsed - i * STAGGER) / DURATION, 0), 1);
        // ease-in-out cubic
        const eased = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
        reveal[route.name] = eased;
        if (t < 1) allDone = false;
      });
      setRouteReveal(reveal);
      if (!allDone) animRef.current = requestAnimationFrame(step);
    };
    animRef.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(animRef.current);
  }, [routes]);

  useEffect(() => {
    if (!mapRef.current) return;
    const map = mapRef.current.getMap();

    if (focusedTurnCoord) {
      // Execute breathtaking route scrubbing sweep highlight
      map.flyTo({ center: [focusedTurnCoord[1], focusedTurnCoord[0]], zoom: 17, pitch: 60, duration: 1200 });
      return;
    }

    if (routes.length > 0) {
      const allCoords = routes.flatMap(r => r.coords);
      if (allCoords.length > 0) {
        const lats = allCoords.map(c => c[0]);
        const lngs = allCoords.map(c => c[1]);
        const bounds = [
          [Math.min(...lngs), Math.min(...lats)],
          [Math.max(...lngs), Math.max(...lats)]
        ];
        map.fitBounds(bounds, { padding: 80, duration: 1500, pitch: 45 });
      }
    } else if (origin && dest) {
      const bounds = [
        [Math.min(origin.coords[1], dest.coords[1]), Math.min(origin.coords[0], dest.coords[0])],
        [Math.max(origin.coords[1], dest.coords[1]), Math.max(origin.coords[0], dest.coords[0])]
      ];
      map.fitBounds(bounds, { padding: 120, duration: 1500, pitch: 45 });
    } else if (origin) {
      map.flyTo({ center: [origin.coords[1], origin.coords[0]], zoom: 15, duration: 1500, pitch: 45 });
    } else if (dest) {
      map.flyTo({ center: [dest.coords[1], dest.coords[0]], zoom: 15, duration: 1500, pitch: 45 });
    } else {
      map.flyTo({ center: [-86.5264, 39.1660], zoom: 14, duration: 1500, pitch: 45 });
    }
  }, [routes, origin, dest, focusedTurnCoord]);

  return (
    <div className="w-full h-full bg-slate-200 rounded-[2rem] overflow-hidden shadow-[0_20px_50px_rgba(8,_112,_184,_0.14)] border-[10px] border-white relative z-0">
      <Map
        ref={mapRef}
        initialViewState={{
          longitude: -86.5264,
          latitude: 39.1660,
          zoom: 14,
          pitch: 45,
          bearing: -10
        }}
        mapStyle="https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json"
        interactive={true}
      >
        {[...routes]
          .sort((a, b) => {
            if (a.name === selectedRouteName) return 1;
            if (b.name === selectedRouteName) return -1;
            return 0;
          })
          .map(route => {
          const isSelected = selectedRouteName === route.name;

          // Each route always keeps its own color — visible and distinct in 3D
          const ROUTE_COLORS: Record<string, string> = {
            'Fastest Route': '#ef4444',
            'Easiest Route': '#22c55e',
            'Balanced Route': '#2563eb',
          };
          const routeColor = ROUTE_COLORS[route.name] ?? '#2563eb';

          const lineCoords: [number, number][] = [...route.coords];

          // Snap the line to user pins if they're not already the endpoints.
          const prependOrigin = origin && lineCoords.length > 0;
          if (prependOrigin) {
            const [olat, olng] = origin!.coords;
            const [slat, slng] = lineCoords[0];
            const distSq = Math.pow(olat - slat, 2) + Math.pow(olng - slng, 2);
            if (distSq > 1e-8) {
              lineCoords.unshift(origin!.coords);
            }
          } else if (origin && lineCoords.length === 0) {
            lineCoords.push(origin.coords);
          }

          const appendDest = dest && lineCoords.length > 0;
          if (appendDest) {
            const [dlat, dlng] = dest!.coords;
            const [elat, elng] = lineCoords[lineCoords.length - 1];
            const distSq = Math.pow(dlat - elat, 2) + Math.pow(dlng - elng, 2);
            if (distSq > 1e-8) {
              lineCoords.push(dest!.coords);
            }
          } else if (dest && lineCoords.length === 0) {
            lineCoords.push(dest.coords);
          }

          const allGeoJsonCoords = lineCoords.map(c => [c[1], c[0]]);
          const reveal = routeReveal[route.name] ?? 1;
          const visibleCount = Math.max(2, Math.round(allGeoJsonCoords.length * reveal));
          const geoJsonCoords = allGeoJsonCoords.slice(0, visibleCount);

          const geojson: any = {
            type: 'Feature',
            properties: {},
            geometry: { type: 'LineString', coordinates: geoJsonCoords }
          };

          // Always render the same stable layer IDs — control visibility via opacity.
          // This prevents MapLibre from adding/removing layers when isSelected changes,
          // which would cause layer-ID conflicts and broken rendering.
          return (
            <Source key={route.name} id={`route-${route.name}`} type="geojson" data={geojson}>
              <Layer id={`route-glow-${route.name}`} type="line" paint={{
                'line-color': routeColor,
                'line-width': 28,
                'line-opacity': isSelected ? 0.18 : 0,
                'line-blur': 12,
              }} />
              <Layer id={`route-bg-${route.name}`} type="line" paint={{
                'line-color': '#ffffff',
                'line-width': 12,
                'line-opacity': isSelected ? 1 : 0,
              }} />
              <Layer id={`route-core-${route.name}`} type="line" paint={{
                'line-color': routeColor,
                'line-width': isSelected ? 7 : 4,
                'line-opacity': isSelected ? 1 : 0.55,
              }} />
            </Source>
          );
        })}

        {origin && (
          <Marker longitude={origin.coords[1]} latitude={origin.coords[0]} anchor="bottom">
            <div className="relative flex items-center justify-center w-12 h-12">
              <div className="absolute bottom-2 w-4 h-2 bg-black/40 blur-[3px] rounded-full z-0" />
              <div className="flex items-center justify-center w-10 h-10 rounded-full shadow-xl border-[3px] border-white bg-emerald-500 z-10 relative mb-1">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0"/><circle cx="12" cy="10" r="3"/></svg>
              </div>
            </div>
          </Marker>
        )}

        {dest && (
          <Marker longitude={dest.coords[1]} latitude={dest.coords[0]} anchor="bottom">
            <div className="relative flex items-center justify-center w-12 h-12">
              <div className="absolute bottom-2 w-4 h-2 bg-black/40 blur-[3px] rounded-full z-0" />
              <div className="flex items-center justify-center w-10 h-10 rounded-full shadow-xl border-[3px] border-white bg-rose-500 z-10 relative mb-1">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" x2="4" y1="22" y2="15"/></svg>
              </div>
            </div>
          </Marker>
        )}

        {focusedTurnCoord && (
          <Marker longitude={focusedTurnCoord[1]} latitude={focusedTurnCoord[0]} anchor="center">
            <div className="relative flex items-center justify-center">
               <div className="w-20 h-20 rounded-full bg-rose-500/30 animate-ping absolute pointer-events-none" />
               <div className="w-5 h-5 rounded-full bg-rose-500 border-2 border-white shadow-[0_0_20px_rgba(244,63,94,0.9)] relative z-10 pointer-events-none" />
            </div>
          </Marker>
        )}
      </Map>
    </div>
  );
};
