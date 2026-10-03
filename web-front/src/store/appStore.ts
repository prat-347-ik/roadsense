import { create } from 'zustand';

interface AppState {
  isSidebarCollapsed: boolean;
  toggleSidebar: () => void;
  mapWidth: number;
  setMapWidth: (width: number) => void;
  isMapVisible: boolean;
  toggleMapVisibility: () => void;
  isLiveConnected: boolean;
  setLiveConnected: (status: boolean) => void;
}

export const useAppStore = create<AppState>((set) => ({
  isSidebarCollapsed: false,
  toggleSidebar: () => set((state) => ({ isSidebarCollapsed: !state.isSidebarCollapsed })),
  mapWidth: 400,
  setMapWidth: (width) => set({ mapWidth: width }),
  isMapVisible: true,
  toggleMapVisibility: () => set((state) => ({ isMapVisible: !state.isMapVisible })),
  isLiveConnected: true,
  setLiveConnected: (status) => set({ isLiveConnected: status }),
}));
