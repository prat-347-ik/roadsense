import { useViolationStore } from "../../store/violationStore";
import { VIOLATION_TYPES } from "../../config/violationTypes";

export default function ViolationFilters() {
  const { filters, setFilter, clearFilters } = useViolationStore();

  return (
    <div className="flex flex-wrap items-center gap-4 p-4 border-b border-border bg-card">
      <div className="space-y-1">
        <label className="text-xs text-muted-foreground font-medium uppercase tracking-wider">Violation Type</label>
        <select 
          className="w-[160px] h-9 rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary"
          value={filters.type}
          onChange={(e) => setFilter("type", e.target.value)}
        >
          <option value="All">All Types</option>
          {VIOLATION_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>

      <div className="space-y-1">
        <label className="text-xs text-muted-foreground font-medium uppercase tracking-wider">Severity</label>
        <select 
          className="w-[140px] h-9 rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary"
          value={filters.severity}
          onChange={(e) => setFilter("severity", e.target.value)}
        >
          <option value="All">All</option>
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
      </div>

      <div className="space-y-1">
        <label className="text-xs text-muted-foreground font-medium uppercase tracking-wider">Time</label>
        <select 
          className="w-[160px] h-9 rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary"
          value={filters.timeRange}
          onChange={(e) => setFilter("timeRange", e.target.value)}
        >
          <option value="Last 1 Hour">Last 1 Hour</option>
          <option value="Last 24 Hours">Last 24 Hours</option>
          <option value="Last 7 Days">Last 7 Days</option>
        </select>
      </div>

      <div className="space-y-1">
        <label className="text-xs text-muted-foreground font-medium uppercase tracking-wider">Status</label>
        <select 
          className="w-[140px] h-9 rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary"
          value={filters.status}
          onChange={(e) => setFilter("status", e.target.value)}
        >
          <option value="All">All</option>
          <option value="new">New</option>
          <option value="reviewed">Reviewed</option>
          <option value="reported">Reported</option>
        </select>
      </div>

      <div className="mt-5">
        <button 
          onClick={clearFilters}
          className="h-9 px-4 rounded-md border border-input bg-background hover:bg-accent hover:text-accent-foreground text-sm font-medium transition-colors"
        >
          Clear Filters
        </button>
      </div>
    </div>
  );
}
