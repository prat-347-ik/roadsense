import { useEffect } from "react";
import { useViolationStore } from "../store/violationStore";
import { mockViolations } from "../data/mockViolations";
import MapView from "../components/map/MapView";
import ViolationFeed from "../components/violations/ViolationFeed";
import ViolationDetails from "../components/violations/ViolationDetails";

export default function Dashboard() {
  const { setViolations, violations, selectedViolationId } = useViolationStore();

  useEffect(() => {
    // Simulate initial data load
    setViolations(mockViolations);
  }, [setViolations]);

  const stats = {
    total: violations.length,
    critical: violations.filter(v => v.severity === 'critical').length,
    activeCameras: 18,
    vehiclesDetected: 8492
  };

  return (
    <div className="flex flex-col h-full overflow-hidden p-6 gap-6 bg-background relative">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">System Overview</h1>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-4 gap-4">
        <div className="p-6 rounded-lg border border-border bg-card">
          <p className="text-sm text-muted-foreground font-medium mb-1">Total Violations</p>
          <p className="text-3xl font-bold">{stats.total.toLocaleString()}</p>
        </div>
        <div className="p-6 rounded-lg border border-border bg-card">
          <p className="text-sm text-muted-foreground font-medium mb-1">Critical Violations</p>
          <p className="text-3xl font-bold text-red-500">{stats.critical}</p>
        </div>
        <div className="p-6 rounded-lg border border-border bg-card">
          <p className="text-sm text-muted-foreground font-medium mb-1">Active Cameras</p>
          <p className="text-3xl font-bold">{stats.activeCameras}</p>
        </div>
        <div className="p-6 rounded-lg border border-border bg-card">
          <p className="text-sm text-muted-foreground font-medium mb-1">Vehicles Detected</p>
          <p className="text-3xl font-bold">{stats.vehiclesDetected.toLocaleString()}</p>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex gap-6 overflow-hidden min-h-0 relative">
        <div className="flex-1 border border-border rounded-lg bg-card overflow-hidden relative z-0">
          <MapView />
        </div>

        <div className="w-[400px] border border-border rounded-lg bg-card flex flex-col z-10">
          <div className="p-4 border-b border-border font-semibold flex justify-between items-center bg-card">
            <span>Live Violation Feed</span>
            <span className="text-xs font-normal text-muted-foreground flex items-center gap-2">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
              </span>
              Live Updates
            </span>
          </div>
          <ViolationFeed />
        </div>

        {selectedViolationId && <ViolationDetails />}
      </div>
    </div>
  );
}
