import { useEffect } from "react";
import { MapContainer, TileLayer, Marker, Popup, useMap, Polygon } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { useViolationStore } from "../../store/violationStore";
import { VIOLATION_COLORS } from "../../config/violationTypes";
import type { Violation } from "../../types";
import ViolationLegend from "./ViolationLegend";
import { Crosshair } from "lucide-react";

// Fix for default marker icon issues in Leaflet with bundlers
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
});

// Component to handle map center updates
function MapUpdater({ center, zoom }: { center: [number, number]; zoom: number }) {
  const map = useMap();
  useEffect(() => {
    map.flyTo(center, zoom, { duration: 0.5 });
  }, [center, zoom, map]);
  return null;
}

const WORLD_BOUNDS: [number, number][] = [
  [-90, -180],
  [90, -180],
  [90, 180],
  [-90, 180]
];

// Rough bounding polygon for Vashi, Navi Mumbai
const VASHI_BOUNDS: [number, number][] = [
  [19.088, 72.982],
  [19.088, 73.012],
  [19.060, 73.012],
  [19.060, 72.982]
];

export default function MapView() {
  const { violations, selectedViolationId, selectViolation, mapCenter, mapZoom, filters, setMapCenter, setMapZoom } = useViolationStore();

  const filteredViolations = violations.filter(v => {
    if (filters.type !== "All" && v.type !== filters.type) return false;
    if (filters.severity !== "All" && v.severity !== filters.severity) return false;
    if (filters.status !== "All" && v.status !== filters.status) return false;
    return true;
  });

  const createCustomIcon = (violation: Violation, isSelected: boolean) => {
    const color = VIOLATION_COLORS[violation.type] || VIOLATION_COLORS.Other;
    
    return L.divIcon({
      className: "custom-marker",
      html: `
        <div class="relative flex items-center justify-center w-8 h-8 ${isSelected ? 'scale-125 z-50' : 'hover:scale-110'} transition-transform">
          <div class="absolute w-full h-full rounded-full opacity-30 ${isSelected ? 'animate-ping' : ''}" style="background-color: ${color}"></div>
          <div class="w-4 h-4 rounded-full border-2 border-white shadow-lg" style="background-color: ${color}"></div>
        </div>
      `,
      iconSize: [32, 32],
      iconAnchor: [16, 16],
    });
  };

  const focusVashi = () => {
    setMapCenter([19.074, 72.997]);
    setMapZoom(14);
  };

  return (
    <div className="w-full h-full relative z-0">
      <MapContainer 
        center={mapCenter} 
        zoom={mapZoom} 
        className="w-full h-full"
        zoomControl={false}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          className="map-tiles"
        />
        <MapUpdater center={mapCenter} zoom={mapZoom} />
        
        {/* Mask to darken areas outside Vashi */}
        <Polygon 
          positions={[WORLD_BOUNDS, VASHI_BOUNDS]}
          pathOptions={{ color: 'transparent', fillColor: '#000000', fillOpacity: 0.7 }}
        />

        {filteredViolations.map((violation) => (
          <Marker
            key={violation.id}
            position={[violation.latitude, violation.longitude]}
            icon={createCustomIcon(violation, selectedViolationId === violation.id)}
            eventHandlers={{
              click: () => {
                selectViolation(violation.id);
              },
            }}
          >
            <Popup className="custom-popup">
              <div className="font-semibold">{violation.type}</div>
              <div className="text-xs text-muted-foreground">{violation.location}</div>
            </Popup>
          </Marker>
        ))}
      </MapContainer>
      <ViolationLegend />
      
      <button 
        onClick={focusVashi}
        title="Focus on Vashi Area"
        className="absolute top-4 right-4 z-[1000] p-2 bg-card border border-border text-foreground hover:bg-accent hover:text-accent-foreground rounded-md shadow-lg transition-colors flex items-center justify-center gap-2"
      >
        <Crosshair className="w-5 h-5" />
        <span className="text-sm font-medium pr-1">Locate Vashi</span>
      </button>
    </div>
  );
}
