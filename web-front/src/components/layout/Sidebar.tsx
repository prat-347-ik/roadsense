import { NavLink } from "react-router-dom";
import { 
  LayoutDashboard, 
  Activity, 
  AlertTriangle, 
  Map, 
  BarChart3, 
  FileText, 
  Video, 
  Settings, 
  User,
  PanelLeftClose,
  PanelLeftOpen
} from "lucide-react";
import { useAppStore } from "../../store/appStore";
import { cn } from "../../lib/utils";

const NAV_ITEMS = [
  { label: "Dashboard", icon: LayoutDashboard, path: "/dashboard" },
  { label: "Live Monitor", icon: Activity, path: "/live-monitor" },
  { label: "Violations", icon: AlertTriangle, path: "/violations" },
  { label: "Map", icon: Map, path: "/map" },
  { label: "Analytics", icon: BarChart3, path: "/analytics" },
  { label: "Reports", icon: FileText, path: "/reports" },
  { label: "Cameras", icon: Video, path: "/cameras" },
];

export default function Sidebar() {
  const { isSidebarCollapsed, toggleSidebar, isLiveConnected } = useAppStore();

  return (
    <aside 
      className={cn(
        "fixed top-0 left-0 h-screen bg-card border-r border-border transition-all duration-300 z-50 flex flex-col",
        isSidebarCollapsed ? "w-[64px]" : "w-[240px]"
      )}
    >
      <div className="h-16 flex items-center justify-between px-4 border-b border-border">
        {!isSidebarCollapsed && (
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded bg-primary flex items-center justify-center">
              <Activity className="w-5 h-5 text-primary-foreground" />
            </div>
            <span className="font-bold text-lg tracking-tight">RoadSense</span>
          </div>
        )}
        {isSidebarCollapsed && (
          <div className="w-8 h-8 rounded bg-primary flex items-center justify-center mx-auto">
            <Activity className="w-5 h-5 text-primary-foreground" />
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto py-4 px-3 flex flex-col gap-1">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            title={isSidebarCollapsed ? item.label : undefined}
            className={({ isActive }) => cn(
              "flex items-center gap-3 px-3 py-2 rounded-md transition-colors",
              isActive 
                ? "bg-accent text-accent-foreground font-medium" 
                : "text-muted-foreground hover:text-foreground hover:bg-accent/50",
              isSidebarCollapsed && "justify-center px-0"
            )}
          >
            <item.icon className="w-5 h-5 flex-shrink-0" />
            {!isSidebarCollapsed && <span>{item.label}</span>}
          </NavLink>
        ))}

        <div className="my-4 border-t border-border" />

        <NavLink
          to="/settings"
          title={isSidebarCollapsed ? "Settings" : undefined}
          className={({ isActive }) => cn(
            "flex items-center gap-3 px-3 py-2 rounded-md transition-colors",
            isActive 
              ? "bg-accent text-accent-foreground font-medium" 
              : "text-muted-foreground hover:text-foreground hover:bg-accent/50",
            isSidebarCollapsed && "justify-center px-0"
          )}
        >
          <Settings className="w-5 h-5 flex-shrink-0" />
          {!isSidebarCollapsed && <span>Settings</span>}
        </NavLink>
        
        <NavLink
          to="/profile"
          title={isSidebarCollapsed ? "Profile" : undefined}
          className={({ isActive }) => cn(
            "flex items-center gap-3 px-3 py-2 rounded-md transition-colors",
            isActive 
              ? "bg-accent text-accent-foreground font-medium" 
              : "text-muted-foreground hover:text-foreground hover:bg-accent/50",
            isSidebarCollapsed && "justify-center px-0"
          )}
        >
          <User className="w-5 h-5 flex-shrink-0" />
          {!isSidebarCollapsed && <span>Profile</span>}
        </NavLink>
      </div>

      <div className="p-4 border-t border-border mt-auto">
        <button 
          onClick={toggleSidebar}
          className="flex w-full items-center justify-center gap-2 text-muted-foreground hover:text-foreground p-2 rounded-md hover:bg-accent/50 transition-colors"
        >
          {isSidebarCollapsed ? <PanelLeftOpen className="w-5 h-5" /> : <PanelLeftClose className="w-5 h-5" />}
          {!isSidebarCollapsed && <span>Collapse</span>}
        </button>
        
        {!isSidebarCollapsed && (
          <div className="mt-4 flex items-center gap-2 text-sm text-muted-foreground">
            <div className={cn("w-2 h-2 rounded-full", isLiveConnected ? "bg-green-500" : "bg-red-500")} />
            System Operational
          </div>
        )}
      </div>
    </aside>
  );
}
