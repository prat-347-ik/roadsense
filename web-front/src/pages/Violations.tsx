import { useViolationStore } from "../store/violationStore";
import { Search } from "lucide-react";
import ViolationFilters from "../components/violations/ViolationFilters";
import ViolationDetails from "../components/violations/ViolationDetails";
import { SEVERITY_COLORS } from "../config/violationTypes";

export default function Violations() {
  const { violations, filters, selectedViolationId, selectViolation } = useViolationStore();

  const filteredViolations = violations.filter(v => {
    if (filters.type !== "All" && v.type !== filters.type) return false;
    if (filters.severity !== "All" && v.severity !== filters.severity) return false;
    if (filters.status !== "All" && v.status !== filters.status) return false;
    return true;
  });

  return (
    <div className="flex flex-col h-full overflow-hidden bg-background relative">
      <div className="p-6 border-b border-border pb-4 flex justify-between items-center">
        <h1 className="text-2xl font-bold tracking-tight">Violations Registry</h1>
        
        <div className="relative w-64">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <input 
            type="text" 
            placeholder="Search vehicle or ID..." 
            className="w-full h-9 bg-accent/50 border border-border rounded-md pl-9 pr-4 py-2 text-sm focus:ring-1 focus:ring-primary focus:outline-none"
          />
        </div>
      </div>

      <ViolationFilters />

      <div className="flex-1 overflow-auto p-6 relative">
        <div className="rounded-md border border-border overflow-hidden">
          <table className="w-full text-sm text-left">
            <thead className="bg-muted text-muted-foreground border-b border-border text-xs uppercase tracking-wider">
              <tr>
                <th className="px-4 py-3 font-medium">Type</th>
                <th className="px-4 py-3 font-medium">Time</th>
                <th className="px-4 py-3 font-medium">Location</th>
                <th className="px-4 py-3 font-medium">Vehicle</th>
                <th className="px-4 py-3 font-medium">Conf.</th>
                <th className="px-4 py-3 font-medium">Severity</th>
                <th className="px-4 py-3 font-medium">Camera</th>
                <th className="px-4 py-3 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {filteredViolations.map((v) => (
                <tr 
                  key={v.id} 
                  onClick={() => selectViolation(v.id)}
                  className={`hover:bg-accent/50 cursor-pointer transition-colors ${selectedViolationId === v.id ? 'bg-accent/80' : ''}`}
                >
                  <td className="px-4 py-3 font-medium">{v.type}</td>
                  <td className="px-4 py-3 text-muted-foreground">{new Date(v.timestamp).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' })}</td>
                  <td className="px-4 py-3">{v.location}</td>
                  <td className="px-4 py-3 font-mono">{v.vehicleNumber || '---'}</td>
                  <td className="px-4 py-3">{v.confidence}%</td>
                  <td className="px-4 py-3 font-medium" style={{ color: SEVERITY_COLORS[v.severity] }}>
                    {v.severity.toUpperCase()}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{v.cameraId}</td>
                  <td className="px-4 py-3">
                    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-secondary text-secondary-foreground capitalize">
                      {v.status}
                    </span>
                  </td>
                </tr>
              ))}
              {filteredViolations.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-muted-foreground">
                    No violations found matching filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {selectedViolationId && <ViolationDetails />}
    </div>
  );
}
