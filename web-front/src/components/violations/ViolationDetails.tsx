import { useViolationStore } from "../../store/violationStore";
import { X, MapPin, Clock, Camera, Car, ShieldAlert, CheckCircle, AlertOctagon } from "lucide-react";
import { VIOLATION_COLORS, SEVERITY_COLORS } from "../../config/violationTypes";

export default function ViolationDetails() {
  const { violations, selectedViolationId, selectViolation } = useViolationStore();
  
  const violation = violations.find(v => v.id === selectedViolationId);

  if (!violation) return null;

  const color = VIOLATION_COLORS[violation.type] || VIOLATION_COLORS.Other;
  const severityColor = SEVERITY_COLORS[violation.severity];

  return (
    <div className="absolute top-0 right-0 w-[400px] h-full bg-card border-l border-border shadow-2xl flex flex-col z-50 animate-in slide-in-from-right duration-300">
      <div className="p-4 border-b border-border flex items-center justify-between bg-accent/30">
        <div className="flex items-center gap-3">
          <div className="w-3 h-3 rounded-full" style={{ backgroundColor: color }} />
          <h2 className="font-semibold text-lg">{violation.type}</h2>
        </div>
        <button 
          onClick={() => selectViolation(null)}
          className="p-1 hover:bg-accent rounded-md transition-colors"
        >
          <X className="w-5 h-5 text-muted-foreground" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* Evidence Image Placeholder */}
        <div className="w-full aspect-video bg-black rounded-lg overflow-hidden relative border border-border group cursor-pointer">
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="text-muted-foreground font-mono text-sm">EVIDENCE_IMG_NOT_FOUND</span>
          </div>
          {/* Simulated bounding box */}
          <div className="absolute top-1/4 left-1/3 w-1/3 h-1/2 border-2 border-red-500 bg-red-500/20"></div>
          
          <div className="absolute bottom-2 right-2 px-2 py-1 bg-black/80 text-xs rounded text-white backdrop-blur-sm">
            CONFIDENCE: {violation.confidence}%
          </div>
        </div>

        {/* Details Grid */}
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-1.5 text-muted-foreground text-xs font-medium uppercase tracking-wider">
              <Clock className="w-3.5 h-3.5" /> Time
            </div>
            <div className="text-sm font-medium">
              {new Date(violation.timestamp).toLocaleString()}
            </div>
          </div>

          <div className="space-y-1">
            <div className="flex items-center gap-1.5 text-muted-foreground text-xs font-medium uppercase tracking-wider">
              <MapPin className="w-3.5 h-3.5" /> Location
            </div>
            <div className="text-sm font-medium">
              {violation.location}
            </div>
          </div>

          <div className="space-y-1">
            <div className="flex items-center gap-1.5 text-muted-foreground text-xs font-medium uppercase tracking-wider">
              <Camera className="w-3.5 h-3.5" /> Source
            </div>
            <div className="text-sm font-medium">
              {violation.cameraId}
            </div>
          </div>

          <div className="space-y-1">
            <div className="flex items-center gap-1.5 text-muted-foreground text-xs font-medium uppercase tracking-wider">
              <AlertOctagon className="w-3.5 h-3.5" /> Severity
            </div>
            <div className="text-sm font-medium" style={{ color: severityColor }}>
              {violation.severity.toUpperCase()}
            </div>
          </div>

          <div className="space-y-1">
            <div className="flex items-center gap-1.5 text-muted-foreground text-xs font-medium uppercase tracking-wider">
              <Car className="w-3.5 h-3.5" /> Vehicle
            </div>
            <div className="text-sm font-medium">
              {violation.vehicleNumber || "UNKNOWN"}
            </div>
          </div>

          <div className="space-y-1">
            <div className="flex items-center gap-1.5 text-muted-foreground text-xs font-medium uppercase tracking-wider">
              <ShieldAlert className="w-3.5 h-3.5" /> Status
            </div>
            <div className="text-sm font-medium capitalize">
              {violation.status}
            </div>
          </div>
        </div>

        <div className="pt-6 border-t border-border flex gap-3">
          <button className="flex-1 bg-primary text-primary-foreground py-2 rounded-md font-medium hover:bg-primary/90 transition-colors flex items-center justify-center gap-2">
            <CheckCircle className="w-4 h-4" />
            Mark Reviewed
          </button>
          <button className="flex-1 bg-accent text-accent-foreground py-2 rounded-md font-medium hover:bg-accent/80 transition-colors">
            Generate Report
          </button>
        </div>
      </div>
    </div>
  );
}
