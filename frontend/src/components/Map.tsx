import React, { useEffect, useRef } from 'react';
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
        <Layer
          id="3d-buildings"
          source="carto"
          source-layer="building"
          type="fill-extrusion"
          minzoom={15}
          paint={{
            'fill-extrusion-color': '#e2e8f0',
            'fill-extrusion-height': ['get', 'render_height'],
            'fill-extrusion-base': ['get', 'render_min_height'],
            'fill-extrusion-opacity': 0.8
          }}
        />

        {routes.map(route => {
          const isSelected = selectedRouteName === route.name;
          const routeColor = isSelected ? '#2563eb' : '#94a3b8';
          
          const fullPositions = [...route.coords] as [number, number][];
          if (origin && fullPositions.length > 0) fullPositions.unshift(origin.coords);
          if (dest && fullPositions.length > 0) fullPositions.push(dest.coords);

          // MapLibre requires [lng, lat] arrays strictly
          const geoJsonCoords = fullPositions.map(c => [c[1], c[0]]);

          const geojson: any = {
            type: 'Feature',
            properties: {},
            geometry: { type: 'LineString', coordinates: geoJsonCoords }
          };

          return (
            <Source key={route.name} id={`route-${route.name}`} type="geojson" data={geojson}>
              {isSelected ? (
                <>
                  <Layer id={`route-glow-${route.name}`} type="line" paint={{ 'line-color': routeColor, 'line-width': 26, 'line-opacity': 0.15, 'line-blur': 10 }} />
                  <Layer id={`route-bg-${route.name}`} type="line" paint={{ 'line-color': '#ffffff', 'line-width': 10 }} />
                  <Layer id={`route-core-${route.name}`} type="line" paint={{ 'line-color': routeColor, 'line-width': 6 }} />
                </>
              ) : (
                <Layer id={`route-unselected-${route.name}`} type="line" paint={{ 'line-color': routeColor, 'line-width': 5, 'line-opacity': 0.65 }} />
              )}
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
