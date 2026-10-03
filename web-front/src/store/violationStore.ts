import { create } from 'zustand';
import type { Violation, ViolationType, Severity } from '../types';

interface Filters {
  type: ViolationType | "All";
  severity: Severity | "All";
  timeRange: string;
  cameraId: string | "All";
  status: string | "All";
}

interface ViolationState {
  violations: Violation[];
  setViolations: (violations: Violation[]) => void;
  selectedViolationId: string | null;
  selectViolation: (id: string | null) => void;
  filters: Filters;
  setFilter: (key: keyof Filters, value: any) => void;
  clearFilters: () => void;
  mapCenter: [number, number];
  setMapCenter: (center: [number, number]) => void;
  mapZoom: number;
  setMapZoom: (zoom: number) => void;
}

const initialFilters: Filters = {
  type: "All",
  severity: "All",
  timeRange: "Last 24 Hours",
  cameraId: "All",
  status: "All"
};

export const useViolationStore = create<ViolationState>((set) => ({
  violations: [],
  setViolations: (violations) => set({ violations }),
  selectedViolationId: null,
  selectViolation: (id) => set({ selectedViolationId: id }),
  filters: initialFilters,
  setFilter: (key, value) => set((state) => ({ filters: { ...state.filters, [key]: value } })),
  clearFilters: () => set({ filters: initialFilters }),
  mapCenter: [19.074, 72.997], // default to Vashi, Navi Mumbai
  setMapCenter: (center) => set({ mapCenter: center }),
  mapZoom: 14,
  setMapZoom: (zoom) => set({ mapZoom: zoom }),
}));
