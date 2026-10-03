import { Bell, Search, UserCircle } from "lucide-react";
import { useAppStore } from "../../store/appStore";

export default function TopBar() {
  const { isLiveConnected } = useAppStore();

  return (
    <header className="h-16 border-b border-border bg-card flex items-center justify-between px-6 z-40">
      <div className="flex-1 flex items-center gap-4">
        <div className="relative w-64">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <input 
            type="text" 
            placeholder="Search violations, cameras..." 
            className="w-full bg-accent/50 border-none rounded-md pl-9 pr-4 py-2 text-sm focus:ring-1 focus:ring-primary focus:outline-none"
          />
        </div>
      </div>
      
      <div className="flex items-center gap-6">
        <div className="flex items-center gap-2 text-sm font-medium">
          <span className="relative flex h-3 w-3">
            {isLiveConnected && <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>}
            <span className={`relative inline-flex rounded-full h-3 w-3 ${isLiveConnected ? 'bg-green-500' : 'bg-red-500'}`}></span>
          </span>
          <span className="text-muted-foreground">Live Monitoring</span>
        </div>
        
        <button className="relative text-muted-foreground hover:text-foreground transition-colors">
          <Bell className="w-5 h-5" />
          <span className="absolute -top-1 -right-1 w-2 h-2 bg-red-500 rounded-full"></span>
        </button>

        <div className="w-px h-6 bg-border mx-2"></div>

        <button className="flex items-center gap-2 hover:opacity-80 transition-opacity">
          <div className="w-8 h-8 rounded-full bg-accent flex items-center justify-center border border-border">
            <UserCircle className="w-6 h-6 text-muted-foreground" />
          </div>
          <div className="text-sm text-left">
            <p className="font-medium leading-none">Admin User</p>
            <p className="text-xs text-muted-foreground">Command Center</p>
          </div>
        </button>
      </div>
    </header>
  );
}
