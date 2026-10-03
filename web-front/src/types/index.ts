export type ViolationType = "Signal Jump" | "No Helmet" | "Wrong Lane" | "Triple Riding" | "Other";
export type Severity = "critical" | "high" | "medium" | "low";
export type ViolationStatus = "new" | "reviewed" | "reported";

export interface Violation {
  id: string;
  type: ViolationType;
  timestamp: string;
  latitude: number;
  longitude: number;
  location: string;
  vehicleNumber?: string;
  vehicleType?: string;
  confidence: number;
  severity: Severity;
  cameraId: string;
  evidenceImage?: string;
  evidenceVideo?: string;
  status: ViolationStatus;
}

export interface Camera {
  id: string;
  name: string;
  location: string;
  status: "online" | "offline";
  lastSeen: string;
  latitude: number;
  longitude: number;
  violationsDetected: number;
}
