import type { Violation } from "../types";

const generateMockViolations = (): Violation[] => {
  const types = ["Signal Jump", "No Helmet", "Wrong Lane", "Triple Riding", "Other"];
  const locations = [
    { name: "Vashi Station Area", lat: 19.0640, lng: 72.9970, cam: "CAM-01" },
    { name: "Sector 17 Junction", lat: 19.0760, lng: 72.9970, cam: "CAM-02" },
    { name: "Vashi Toll Naka", lat: 19.0630, lng: 72.9840, cam: "CAM-03" },
    { name: "Palm Beach Road", lat: 19.0600, lng: 73.0070, cam: "CAM-04" },
    { name: "Inorbit Mall Road", lat: 19.0700, lng: 72.9980, cam: "CAM-05" },
  ];
  const severities = ["critical", "high", "medium", "low"];

  const violations: Violation[] = [];
  const now = new Date();

  for (let i = 0; i < 50; i++) {
    const loc = locations[Math.floor(Math.random() * locations.length)];
    const time = new Date(now.getTime() - Math.random() * 86400000); // within last 24h
    
    // Spread coordinates tightly so they don't leak out of Vashi
    const latOffset = (Math.random() - 0.5) * 0.002;
    const lngOffset = (Math.random() - 0.5) * 0.002;

    violations.push({
      id: `VIO-${Math.floor(1000 + Math.random() * 9000)}-${i}`,
      type: types[Math.floor(Math.random() * types.length)] as any,
      timestamp: time.toISOString(),
      latitude: loc.lat + latOffset,
      longitude: loc.lng + lngOffset,
      location: loc.name,
      vehicleNumber: `MH-04-${Math.floor(1000 + Math.random() * 9000)}`,
      confidence: Math.floor(70 + Math.random() * 29), // 70 to 99
      severity: severities[Math.floor(Math.random() * severities.length)] as any,
      cameraId: loc.cam,
      status: Math.random() > 0.8 ? "reviewed" : "new",
    });
  }

  // Sort descending by timestamp
  return violations.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
};

export const mockViolations = generateMockViolations();
