import { Outlet } from "react-router-dom";
import Sidebar from "./Sidebar";
import TopBar from "./TopBar";
import { useAppStore } from "../../store/appStore";

export default function AppShell() {
  const { isSidebarCollapsed } = useAppStore();

  return (
    <div className="flex h-screen w-full bg-background overflow-hidden">
      {/* Sidebar fixed to left */}
      <Sidebar />
      
      {/* Main content wrapper */}
      <div 
        className="flex flex-col flex-1 transition-all duration-300"
        style={{ marginLeft: isSidebarCollapsed ? '64px' : '240px' }}
      >
        <TopBar />
        <main className="flex-1 overflow-hidden relative">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
