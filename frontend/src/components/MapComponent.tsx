import React, { useEffect } from 'react';
import { MapContainer, TileLayer, Marker, Popup, Polyline, useMap } from 'react-leaflet';
import L from 'leaflet';
import { Observation, IncidentDetail } from '../types/api';
import { Camera, Navigation, AlertCircle } from 'lucide-react';

interface MapComponentProps {
  incident: IncidentDetail;
}

// Helper component to adjust bounds automatically
const AutoFitBounds: React.FC<{ points: [number, number][] }> = ({ points }) => {
  const map = useMap();

  useEffect(() => {
    if (points.length === 0) return;
    if (points.length === 1) {
      map.setView(points[0], 16);
    } else {
      const bounds = L.latLngBounds(points);
      map.fitBounds(bounds, { padding: [40, 40], maxZoom: 17 });
    }
  }, [map, points]);

  return null;
};

export const MapComponent: React.FC<MapComponentProps> = ({ incident }) => {
  const { observations, violation_type } = incident;

  // Sort observations chronologically
  const sortedObs = [...observations].sort((a, b) => new Date(a.ts).getTime() - new Date(b.ts).getTime());
  const points: [number, number][] = sortedObs.map(o => [o.lat, o.lon]);

  // Center point
  const center: [number, number] = points.length > 0 
    ? [
        points.reduce((sum, p) => sum + p[0], 0) / points.length,
        points.reduce((sum, p) => sum + p[1], 0) / points.length,
      ]
    : [18.5204, 73.8567];

  // Helper to create custom HTML pin icon with sequence number
  const createPinIcon = (index: number, obs: Observation) => {
    let pinColor = '#38bdf8'; // sky/default
    if (obs.wrong_way_status === 'confirmed') pinColor = '#10b981'; // green
    if (obs.wrong_way_status === 'rejected') pinColor = '#f43f5e'; // red
    if (violation_type === 'red_light') pinColor = '#f59e0b'; // amber

    return L.divIcon({
      className: 'custom-map-pin',
      html: `
        <div style="
          display: flex;
          align-items: center;
          justify-content: center;
          width: 32px;
          height: 32px;
          border-radius: 50%;
          background: ${pinColor};
          color: white;
          font-weight: 700;
          font-size: 13px;
          font-family: sans-serif;
          box-shadow: 0 0 15px ${pinColor}80, 0 4px 6px rgba(0,0,0,0.5);
          border: 2px solid #ffffff;
        ">
          ${index + 1}
        </div>
      `,
      iconSize: [32, 32],
      iconAnchor: [16, 16],
      popupAnchor: [0, -18],
    });
  };

  return (
    <div className="relative w-full h-[400px] rounded-xl overflow-hidden border border-slate-800 shadow-inner bg-slate-950">
      <MapContainer
        center={center}
        zoom={15}
        scrollWheelZoom={false}
        className="w-full h-full"
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        <AutoFitBounds points={points} />

        {/* Trajectory Polyline */}
        {points.length > 1 && (
          <Polyline
            positions={points}
            pathOptions={{
              color: incident.status === 'rejected' ? '#f43f5e' : '#38bdf8',
              weight: 3,
              dashArray: incident.status === 'rejected' ? '6, 8' : undefined,
              opacity: 0.8,
            }}
          />
        )}

        {/* Individual Observation Pins */}
        {sortedObs.map((obs, idx) => (
          <Marker
            key={obs.id || obs.event_nonce || idx}
            position={[obs.lat, obs.lon]}
            icon={createPinIcon(idx, obs)}
          >
            <Popup>
              <div className="text-xs space-y-1.5 p-1 min-w-[200px]">
                <div className="flex items-center justify-between border-b border-slate-700 pb-1">
                  <span className="font-bold text-slate-100 flex items-center gap-1">
                    <Camera className="w-3.5 h-3.5 text-blue-400" />
                    Point #{idx + 1}
                  </span>
                  <span className="font-mono text-[11px] text-slate-400">{obs.device_id}</span>
                </div>

                <div className="grid grid-cols-2 gap-1 text-[11px] text-slate-300">
                  <div>Time:</div>
                  <div className="font-mono text-slate-100">
                    {new Date(obs.ts).toLocaleTimeString()}
                  </div>
                  <div>Coords:</div>
                  <div className="font-mono text-slate-100 text-[10px]">
                    {obs.lat.toFixed(5)}, {obs.lon.toFixed(5)}
                  </div>
                  {obs.wrong_way_status && (
                    <>
                      <div>Status:</div>
                      <div className="font-semibold capitalize text-blue-300">
                        {obs.wrong_way_status}
                      </div>
                    </>
                  )}
                  {obs.rejection_reason && (
                    <>
                      <div className="text-rose-400">Rejection:</div>
                      <div className="text-rose-300 font-mono text-[10px]">
                        {obs.rejection_reason}
                      </div>
                    </>
                  )}
                </div>

                <div className="text-[10px] text-slate-400 font-mono break-all pt-1 border-t border-slate-800">
                  Nonce: {obs.event_nonce.slice(0, 16)}...
                </div>
              </div>
            </Popup>
          </Marker>
        ))}
      </MapContainer>

      {/* Map Legend Overlay */}
      <div className="absolute top-3 right-3 z-[1000] bg-slate-900/90 backdrop-blur-md border border-slate-700/60 rounded-lg p-2.5 shadow-xl text-xs space-y-1.5 pointer-events-none">
        <div className="text-[11px] font-semibold text-slate-300 uppercase tracking-wider">
          Trajectory Map
        </div>
        <div className="flex items-center gap-2 text-slate-300">
          <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 inline-block"></span>
          <span>Confirmed Progress</span>
        </div>
        <div className="flex items-center gap-2 text-slate-300">
          <span className="w-2.5 h-2.5 rounded-full bg-rose-400 inline-block"></span>
          <span>Rejected Point</span>
        </div>
        <div className="flex items-center gap-2 text-slate-300">
          <span className="w-2.5 h-2.5 rounded-full bg-sky-400 inline-block"></span>
          <span>Unconfirmed</span>
        </div>
      </div>
    </div>
  );
};
