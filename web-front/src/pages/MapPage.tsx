import MapView from "../components/map/MapView";
import ViolationFilters from "../components/violations/ViolationFilters";
import ViolationDetails from "../components/violations/ViolationDetails";
import { useViolationStore } from "../store/violationStore";

export default function MapPage() {
  const { selectedViolationId } = useViolationStore();

  return (
    <div className="flex flex-col h-full overflow-hidden bg-background relative">
      <div className="p-4 border-b border-border bg-card z-10 flex justify-between items-center">
        <h1 className="text-xl font-bold tracking-tight">Geospatial Analysis</h1>
      </div>
      
      <div className="z-10">
        <ViolationFilters />
      </div>

      <div className="flex-1 relative z-0">
        <MapView />
      </div>
      
      {selectedViolationId && <ViolationDetails />}
    </div>
  );
}
