import MapView from "../components/map/MapView";
import ViolationFeed from "../components/violations/ViolationFeed";
import { useViolationStore } from "../store/violationStore";
import { mockCameras } from "../data/mockCameras";
import { Camera, Activity } from "lucide-react";
import ViolationDetails from "../components/violations/ViolationDetails";

export default function LiveMonitor() {
  const { selectedViolationId } = useViolationStore();

  return (
    <div className="flex flex-col h-full overflow-hidden bg-background relative">
      <div className="p-4 border-b border-border flex justify-between items-center bg-card z-10">
        <div className="flex items-center gap-4">
          <h1 className="text-xl font-bold tracking-tight">Live Operations Monitor</h1>
          <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-green-500/10 text-green-500 text-sm font-medium border border-green-500/20">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
            </span>
            SYSTEM ACTIVE
          </div>
        </div>
      </div>

      <div className="flex-1 flex overflow-hidden">
        {/* Left sidebar for camera status */}
        <div className="w-64 border-r border-border bg-card flex flex-col z-10">
          <div className="p-4 border-b border-border font-semibold flex items-center gap-2 text-sm uppercase tracking-wider text-muted-foreground">
            <Camera className="w-4 h-4" /> Camera Status
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-2">
            {mockCameras.map(cam => (
              <div key={cam.id} className="p-3 border border-border rounded-md bg-background">
                <div className="flex justify-between items-start mb-2">
                  <div className="font-semibold text-sm">{cam.id}</div>
                  <div className={`w-2 h-2 rounded-full mt-1 ${cam.status === 'online' ? 'bg-green-500' : 'bg-red-500'}`} />
                </div>
                <div className="text-xs text-muted-foreground truncate">{cam.name}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Main Map */}
        <div className="flex-1 relative z-0">
          <MapView />
        </div>

        {/* Right Feed */}
        <div className="w-[350px] border-l border-border bg-card flex flex-col z-10">
          <div className="p-4 border-b border-border font-semibold flex items-center gap-2 text-sm uppercase tracking-wider text-muted-foreground">
            <Activity className="w-4 h-4" /> Live Feed
          </div>
          <ViolationFeed />
        </div>
      </div>
      
      {selectedViolationId && <ViolationDetails />}
    </div>
  );
}
