import type { Camera } from "../types";

export const mockCameras: Camera[] = [
  {
    id: "CAM-01",
    name: "Vashi Station Area",
    location: "Sector 30A",
    status: "online",
    lastSeen: new Date().toISOString(),
    latitude: 19.0640,
    longitude: 72.9970,
    violationsDetected: 342,
  },
  {
    id: "CAM-02",
    name: "Sector 17 Junction",
    location: "Sector 17",
    status: "online",
    lastSeen: new Date().toISOString(),
    latitude: 19.0760,
    longitude: 72.9970,
    violationsDetected: 1205,
  },
  {
    id: "CAM-03",
    name: "Vashi Toll Naka",
    location: "Highway Bridge",
    status: "offline",
    lastSeen: new Date(Date.now() - 3600000).toISOString(), // 1 hour ago
    latitude: 19.0630,
    longitude: 72.9840,
    violationsDetected: 89,
  },
  {
    id: "CAM-04",
    name: "Palm Beach Road",
    location: "Sector 14",
    status: "online",
    lastSeen: new Date().toISOString(),
    latitude: 19.0600,
    longitude: 73.0070,
    violationsDetected: 56,
  }
];
