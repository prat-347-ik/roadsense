import { 
  IncidentDetail, 
  IncidentStatus, 
  IncidentSummary, 
  LoginResponse, 
  ReviewActionResponse, 
  Reviewer, 
  ViolationType 
} from '../types/api';

const API_BASE = ''; // Uses Vite proxy in development, or relative path in production

let authToken: string | null = null;

export const setAuthToken = (token: string | null) => {
  authToken = token;
};

export const getAuthToken = () => authToken;

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };

  if (authToken) {
    headers['Authorization'] = `Bearer ${authToken}`;
  }

  const url = `${API_BASE}${endpoint}`;
  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let errorDetail = `HTTP ${response.status}: ${response.statusText}`;
    try {
      const errorJson = await response.json();
      if (errorJson.detail) {
        if (typeof errorJson.detail === 'string') {
          errorDetail = errorJson.detail;
        } else if (Array.isArray(errorJson.detail)) {
          errorDetail = errorJson.detail.map((d: any) => d.msg || JSON.stringify(d)).join(', ');
        }
      }
    } catch {
      // Non-JSON response
    }
    throw new Error(errorDetail);
  }

  return response.json();
}

export const api = {
  async login(email: string, password: string): Promise<LoginResponse> {
    const data = await request<LoginResponse>('/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    setAuthToken(data.access_token);
    return data;
  },

  async getMe(): Promise<Reviewer> {
    return request<Reviewer>('/v1/auth/me');
  },

  async getIncidents(params?: {
    status?: IncidentStatus;
    violation_type?: ViolationType;
    limit?: number;
    offset?: number;
  }): Promise<IncidentSummary[]> {
    const query = new URLSearchParams();
    if (params?.status) query.append('status', params.status);
    if (params?.violation_type) query.append('violation_type', params.violation_type);
    if (params?.limit) query.append('limit', params.limit.toString());
    if (params?.offset) query.append('offset', params.offset.toString());

    const qs = query.toString();
    return request<IncidentSummary[]>(`/v1/incidents${qs ? `?${qs}` : ''}`);
  },

  async getIncident(id: number): Promise<IncidentDetail> {
    return request<IncidentDetail>(`/v1/incidents/${id}`);
  },

  async approveIncident(id: number): Promise<ReviewActionResponse> {
    return request<ReviewActionResponse>(`/v1/incidents/${id}/approve`, {
      method: 'POST',
    });
  },

  async rejectIncident(id: number): Promise<ReviewActionResponse> {
    return request<ReviewActionResponse>(`/v1/incidents/${id}/reject`, {
      method: 'POST',
    });
  },
};
