export type ViolationType = 'wrong_side' | 'red_light';

export type IncidentStatus = 
  | 'candidate' 
  | 'corroborated' 
  | 'corroborated_no_evidence' 
  | 'confirmed' 
  | 'rejected';

export interface Reviewer {
  id: number;
  email: string;
  role: string;
  created_at?: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  reviewer: Reviewer;
}

export interface Observation {
  id: number;
  device_id: string;
  violation_type: ViolationType;
  hashed_plate: string;
  lat: number;
  lon: number;
  ts: string;
  event_nonce: string;
  wrong_way_status: 'unconfirmed' | 'confirmed' | 'rejected' | null;
  rejection_reason?: string | null;
  rejection_details?: string | null;
}

export interface EvidenceItem {
  device_id: string;
  event_nonce: string;
  uploaded_at: string | null;
  storage_ref: string | null;
  view_url: string | null;
  presigned_url?: string | null;
  retention_expires_at?: string | null;
}

export interface IncidentSummary {
  id: number;
  violation_type: ViolationType;
  hashed_plate: string;
  status: IncidentStatus;
  window_start: string;
  window_end: string;
  observation_count: number;
  reviewed_by: number | null;
  reviewed_at: string | null;
}

export interface IncidentDetail {
  id: number;
  violation_type: ViolationType;
  hashed_plate: string;
  status: IncidentStatus;
  window_start: string;
  window_end: string;
  reviewed_by: number | null;
  reviewed_at: string | null;
  reviewer_email: string | null;
  rejection_reason?: string | null;
  rejection_details?: string | null;
  observations: Observation[];
  evidence_items: EvidenceItem[];
}

export interface ReviewActionResponse {
  status: string;
  incident_id: number;
  new_status: 'confirmed' | 'rejected';
  reviewed_by: number;
  reviewed_at: string;
}
