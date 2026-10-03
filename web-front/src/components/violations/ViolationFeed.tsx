import { useViolationStore } from "../../store/violationStore";
import { VIOLATION_COLORS, SEVERITY_COLORS } from "../../config/violationTypes";
import { cn } from "../../lib/utils";
import { useRef, useEffect } from "react";

export default function ViolationFeed() {
  const { violations, selectedViolationId, selectViolation, setMapCenter, setMapZoom, filters } = useViolationStore();
  const listRef = useRef<HTMLDivElement>(null);
  
  const filteredViolations = violations.filter(v => {
    if (filters.type !== "All" && v.type !== filters.type) return false;
    if (filters.severity !== "All" && v.severity !== filters.severity) return false;
    if (filters.status !== "All" && v.status !== filters.status) return false;
    return true;
  });

  // Create a sorted copy
  const sortedViolations = [...filteredViolations].sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());

  // Scroll into view when selected
  useEffect(() => {
    if (selectedViolationId && listRef.current) {
      const el = document.getElementById(`violation-${selectedViolationId}`);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
    }
  }, [selectedViolationId]);

  const handleSelect = (violation: typeof violations[0]) => {
    selectViolation(violation.id);
    setMapCenter([violation.latitude, violation.longitude]);
    setMapZoom(16);
  };

  return (
    <div className="flex-1 overflow-y-auto" ref={listRef}>
      <div className="flex flex-col">
        {sortedViolations.map((violation) => {
          const isSelected = selectedViolationId === violation.id;
          const color = VIOLATION_COLORS[violation.type] || VIOLATION_COLORS.Other;
          const severityColor = SEVERITY_COLORS[violation.severity];
          
          return (
            <div 
              key={violation.id}
              id={`violation-${violation.id}`}
              onClick={() => handleSelect(violation)}
              className={cn(
                "p-4 border-b border-border cursor-pointer transition-colors hover:bg-accent/50",
                isSelected ? "bg-accent/80 border-l-4" : "border-l-4 border-l-transparent"
              )}
              style={{ borderLeftColor: isSelected ? color : 'transparent' }}
            >
              <div className="flex justify-between items-start mb-1">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
                  <span className="font-semibold text-sm">{violation.type}</span>
                </div>
                <span className="text-xs text-muted-foreground">
                  {new Date(violation.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                </span>
              </div>
              
              <div className="text-sm text-muted-foreground mb-2">
                {violation.location}
              </div>
              
              <div className="flex items-center justify-between text-xs">
                <div className="flex gap-2">
                  <span className="px-2 py-0.5 rounded-sm bg-background border border-border">
                    Conf: {violation.confidence}%
                  </span>
                  <span className="px-2 py-0.5 rounded-sm" style={{ color: severityColor, backgroundColor: `color-mix(in srgb, ${severityColor} 10%, transparent)`}}>
                    {violation.severity.toUpperCase()}
                  </span>
                </div>
                <span>{violation.cameraId}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
