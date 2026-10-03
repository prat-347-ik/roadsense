import { VIOLATION_COLORS, VIOLATION_TYPES } from "../../config/violationTypes";
import { useViolationStore } from "../../store/violationStore";

export default function ViolationLegend() {
  const { filters, setFilter } = useViolationStore();

  const handleToggle = (type: any) => {
    if (filters.type === type) {
      setFilter("type", "All");
    } else {
      setFilter("type", type);
    }
  };

  return (
    <div className="absolute bottom-6 left-6 z-[1000] bg-card/90 backdrop-blur-sm border border-border rounded-lg p-4 shadow-lg pointer-events-auto">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">Violation Legend</h3>
      <div className="flex flex-col gap-2">
        {VIOLATION_TYPES.map(type => {
          const isSelected = filters.type === type;
          const isFaded = filters.type !== "All" && !isSelected;
          
          return (
            <button 
              key={type} 
              onClick={() => handleToggle(type)}
              className={`flex items-center gap-2 hover:bg-accent hover:text-accent-foreground p-1.5 -mx-1.5 rounded-md transition-all text-left ${isFaded ? 'opacity-40' : 'opacity-100'} ${isSelected ? 'font-bold bg-accent/50' : ''}`}
            >
              <div 
                className={`w-3 h-3 rounded-full transition-all ${isSelected ? 'ring-2 ring-offset-2 ring-offset-card ring-primary' : ''}`} 
                style={{ backgroundColor: VIOLATION_COLORS[type] }} 
              />
              <span className="text-sm">{type}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
