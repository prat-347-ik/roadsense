import React from 'react';
import { 
  AlertTriangle, 
  XOctagon, 
  Compass, 
  Car, 
  Zap, 
  Clock, 
  Info,
  CheckCircle2,
  FileX
} from 'lucide-react';
import { IncidentDetail, IncidentStatus } from '../types/api';

interface RejectionDiagnosticProps {
  incident: IncidentDetail;
}

export const RejectionDiagnostic: React.FC<RejectionDiagnosticProps> = ({ incident }) => {
  const { status, violation_type, rejection_reason, rejection_details, observations } = incident;

  // Render for corroborated_no_evidence
  if (status === 'corroborated_no_evidence') {
    return (
      <div className="rounded-xl border border-amber-500/40 bg-gradient-to-r from-amber-950/40 via-amber-900/20 to-slate-900/60 p-5 shadow-lg">
        <div className="flex items-start gap-4">
          <div className="p-2.5 rounded-lg bg-amber-500/20 text-amber-400 border border-amber-500/30 shrink-0">
            <FileX className="w-6 h-6" />
          </div>
          <div className="flex-1 space-y-1.5">
            <div className="flex items-center gap-2">
              <h3 className="font-semibold text-amber-200 text-base">
                Corroborated Without Video Evidence (TTL Expired)
              </h3>
              <span className="text-xs px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 font-mono">
                TTL Expiration
              </span>
            </div>
            <p className="text-sm text-slate-300 leading-relaxed">
              This violation met multi-device corroboration thresholds (reported by {observations.length} sensors), and evidence upload requests were queued. However, the edge devices did not transmit media before the retrieval deadline expired.
            </p>
            <div className="pt-2 text-xs text-amber-300/80 flex items-center gap-2 font-mono">
              <Info className="w-4 h-4" />
              <span>Reviewer may verify telemetry coordinates or dismiss the candidate.</span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Render for rejected incidents
  if (status === 'rejected') {
    const getReasonContent = () => {
      // Find rejected observation or use incident-level reason
      const rejectedObs = observations.find(o => o.wrong_way_status === 'rejected' || o.rejection_reason);
      const reason = rejection_reason || rejectedObs?.rejection_reason || 'progression_rejection';
      const details = rejection_details || rejectedObs?.rejection_details;

      switch (reason) {
        case 'inconsistent_trajectory':
          return {
            title: 'Auto-Rejected: Inconsistent Vehicle Trajectory',
            tag: 'inconsistent_trajectory',
            icon: Compass,
            color: 'from-rose-950/50 border-rose-500/40 text-rose-300',
            description: details || 'Vehicle trajectory reversed direction or intermediate segment bearing deviated by >60° from overall vector. Flagged as sensor parallax or invalid trajectory rather than genuine wrong-way travel.',
            fixNote: 'This incident was automatically isolated and rejected to eliminate false corroboration from contradictory camera paths.',
          };
        case 'parked':
          return {
            title: 'Auto-Rejected: Stationary / Parked Vehicle',
            tag: 'parked',
            icon: Car,
            color: 'from-orange-950/50 border-orange-500/40 text-orange-300',
            description: details || 'Target vehicle remained stationary (displacement ≤ 8.0 meters over elapsed time). Filtered out stationary vehicle false positives.',
            fixNote: 'Parked vehicles facing against traffic flow are prevented from generating active wrong-way citations.',
          };
        case 'overtaking_artifact':
          return {
            title: 'Auto-Rejected: Solitary Overtaking Artifact',
            tag: 'overtaking_artifact',
            icon: Clock,
            color: 'from-yellow-950/50 border-yellow-500/40 text-yellow-300',
            description: details || 'Solitary unconfirmed observation aged past the 300s corroboration window with no supporting sensor bursts. Categorized as momentary lane overtaking artifact.',
            fixNote: 'Single-camera brief lane crossovers are purged by background sweep to avoid solo camera false-alarms.',
          };
        case 'unrealistic_speed':
          return {
            title: 'Auto-Rejected: Unrealistic Speed / Sensor Glitch',
            tag: 'unrealistic_speed',
            icon: Zap,
            color: 'from-red-950/50 border-red-500/40 text-red-300',
            description: details || 'Calculated speed exceeds physical threshold (> 60.0 m/s / 216 km/h). Rejected as hardware timestamp or coordinate glitch.',
            fixNote: 'Telemetry sanity bounds protect against corrupt burst coordinates.',
          };
        default:
          return {
            title: incident.reviewed_by ? 'Dismissed by Reviewer' : 'Auto-Rejected Violation',
            tag: reason,
            icon: XOctagon,
            color: 'from-slate-900 border-rose-500/30 text-rose-300',
            description: details || (incident.reviewed_by 
              ? `Reviewer determined this incident did not constitute an actionable violation upon inspection.`
              : 'Violation failed automated corroboration checks or was rejected by reviewer decision.'),
            fixNote: incident.reviewed_at ? `Audit logged at ${new Date(incident.reviewed_at).toLocaleString()}` : '',
          };
      }
    };

    const content = getReasonContent();
    const Icon = content.icon;

    return (
      <div className={`rounded-xl border bg-gradient-to-r ${content.color} to-slate-900/70 p-5 shadow-lg space-y-3`}>
        <div className="flex items-start gap-4">
          <div className="p-2.5 rounded-lg bg-rose-500/20 text-rose-400 border border-rose-500/30 shrink-0">
            <Icon className="w-6 h-6" />
          </div>
          <div className="flex-1 space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="font-semibold text-rose-200 text-base">
                {content.title}
              </h3>
              <span className="text-xs px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 font-mono">
                {content.tag}
              </span>
            </div>
            <p className="text-sm text-slate-300 leading-relaxed font-sans">
              {content.description}
            </p>
            {content.fixNote && (
              <div className="text-xs text-rose-400/90 font-mono bg-black/30 px-3 py-2 rounded-lg border border-rose-500/20 flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 shrink-0 text-rose-400" />
                <span>{content.fixNote}</span>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  return null;
};
