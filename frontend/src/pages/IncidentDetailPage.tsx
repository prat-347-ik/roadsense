import React, { useState, useEffect } from 'react';
import { api } from '../services/api';
import { IncidentDetail } from '../types/api';
import { StatusBadge } from '../components/StatusBadge';
import { MapComponent } from '../components/MapComponent';
import { EvidencePlayer } from '../components/EvidencePlayer';
import { RejectionDiagnostic } from '../components/RejectionDiagnostic';
import { 
  ArrowLeft, 
  Check, 
  X, 
  Clock, 
  Camera, 
  AlertCircle, 
  ShieldCheck, 
  CheckCircle2, 
  UserCheck, 
  Fingerprint, 
  RefreshCw,
  Info,
  Calendar,
  Layers
} from 'lucide-react';

interface IncidentDetailPageProps {
  incidentId: number;
  onBack: () => void;
}

export const IncidentDetailPage: React.FC<IncidentDetailPageProps> = ({ incidentId, onBack }) => {
  const [incident, setIncident] = useState<IncidentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const fetchIncident = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getIncident(incidentId);
      setIncident(data);
    } catch (err: any) {
      setError(err.message || `Failed to fetch incident #${incidentId}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchIncident();
  }, [incidentId]);

  const handleApprove = async () => {
    if (!incident || isReviewed) return;
    setActionLoading(true);
    setActionMessage(null);
    try {
      const res = await api.approveIncident(incident.id);
      setActionMessage({
        type: 'success',
        text: `Incident #${incident.id} approved successfully and marked as Confirmed.`,
      });
      // Refresh incident state
      await fetchIncident();
    } catch (err: any) {
      setActionMessage({
        type: 'error',
        text: err.message || 'Failed to approve incident',
      });
    } finally {
      setActionLoading(false);
    }
  };

  const handleReject = async () => {
    if (!incident || isReviewed) return;
    setActionLoading(true);
    setActionMessage(null);
    try {
      const res = await api.rejectIncident(incident.id);
      setActionMessage({
        type: 'success',
        text: `Incident #${incident.id} dismissed and marked as Rejected.`,
      });
      // Refresh incident state
      await fetchIncident();
    } catch (err: any) {
      setActionMessage({
        type: 'error',
        text: err.message || 'Failed to reject incident',
      });
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16 text-center space-y-4">
        <div className="w-10 h-10 border-3 border-blue-500/30 border-t-blue-500 rounded-full animate-spin mx-auto"></div>
        <div className="text-base text-slate-300 font-medium">
          Loading telemetry and evidence for Incident #{incidentId}...
        </div>
      </div>
    );
  }

  if (error || !incident) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-16 text-center space-y-4">
        <div className="p-4 rounded-xl bg-rose-950/60 border border-rose-500/40 text-rose-200 text-sm">
          <AlertCircle className="w-6 h-6 text-rose-400 mx-auto mb-2" />
          <div className="font-semibold text-base">Error Loading Incident</div>
          <p className="mt-1 text-xs text-rose-300/80">{error || 'Incident not found'}</p>
        </div>
        <button
          onClick={onBack}
          className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm font-semibold inline-flex items-center gap-2"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Incident Queue</span>
        </button>
      </div>
    );
  }

  const isReviewed = incident.reviewed_by !== null;
  const isWrongSide = incident.violation_type === 'wrong_side';

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      {/* Top Navigation & Status Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-5">
        <div className="flex items-center gap-4">
          <button
            onClick={onBack}
            className="p-2.5 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 hover:text-white transition-colors"
            title="Back to queue"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <div className="flex flex-wrap items-center gap-2.5">
              <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
                Incident #{incident.id}
              </h1>
              <span className="text-xs uppercase px-2.5 py-1 rounded-md bg-slate-800 border border-slate-700 text-slate-200 font-mono font-bold">
                {isWrongSide ? 'Wrong-Side Driving' : 'Red-Light Infraction'}
              </span>
              <StatusBadge status={incident.status} size="md" />
            </div>
            <p className="text-xs text-slate-400 mt-1 font-mono">
              Clustered Spatio-Temporal Event | {incident.observations.length} Sensor Bursts Recorded
            </p>
          </div>
        </div>

        {/* Action Buttons or Audit Badge */}
        <div className="flex items-center gap-3">
          {isReviewed ? (
            <div className="p-3 rounded-xl bg-purple-950/50 border border-purple-500/40 text-purple-200 text-xs flex items-center gap-2.5">
              <UserCheck className="w-5 h-5 text-purple-400 shrink-0" />
              <div>
                <div className="font-semibold text-purple-100">
                  Reviewed by {incident.reviewer_email || `Reviewer #${incident.reviewed_by}`}
                </div>
                <div className="text-[11px] text-purple-300/80 font-mono">
                  {incident.reviewed_at ? new Date(incident.reviewed_at).toLocaleString() : ''}
                </div>
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-2.5">
              <button
                onClick={handleReject}
                disabled={actionLoading}
                className="px-4 py-2.5 rounded-xl bg-rose-600/20 hover:bg-rose-600/30 border border-rose-500/40 text-rose-300 hover:text-rose-200 text-xs font-semibold flex items-center gap-2 transition-all disabled:opacity-50"
              >
                <X className="w-4 h-4 text-rose-400" />
                <span>Reject / Dismiss</span>
              </button>
              <button
                onClick={handleApprove}
                disabled={actionLoading}
                className="px-5 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold flex items-center gap-2 shadow-lg shadow-emerald-600/20 transition-all disabled:opacity-50"
              >
                {actionLoading ? (
                  <RefreshCw className="w-4 h-4 animate-spin" />
                ) : (
                  <Check className="w-4 h-4" />
                )}
                <span>Approve Violation</span>
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Action Notification Message */}
      {actionMessage && (
        <div
          className={`p-4 rounded-xl border text-xs font-medium flex items-center gap-2.5 ${
            actionMessage.type === 'success'
              ? 'bg-emerald-950/70 border-emerald-500/40 text-emerald-200'
              : 'bg-rose-950/70 border-rose-500/40 text-rose-200'
          }`}
        >
          {actionMessage.type === 'success' ? (
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
          ) : (
            <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
          )}
          <span>{actionMessage.text}</span>
        </div>
      )}

      {/* Diagnostic Callout for Rejected & Missing Evidence */}
      <RejectionDiagnostic incident={incident} />

      {/* Main Grid: Left Column (Map & Telemetry), Right Column (Evidence & Details) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left 7 Columns: Spatial Map & Sensor Burst Table */}
        <div className="lg:col-span-7 space-y-6">
          {/* Spatial Trajectory Map */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wider flex items-center gap-2">
                <Layers className="w-4 h-4 text-blue-400" />
                <span>Spatial Trajectory & Camera Clusters</span>
              </h2>
              <span className="text-xs text-slate-400 font-mono">
                {incident.observations.length} coordinates plotted
              </span>
            </div>
            <MapComponent incident={incident} />
          </div>

          {/* Contributing Observation Telemetry Table */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wider flex items-center gap-2">
                <Camera className="w-4 h-4 text-blue-400" />
                <span>Contributing Observation Bursts</span>
              </h2>
            </div>

            <div className="bg-slate-900/60 border border-slate-800 rounded-xl overflow-hidden shadow-md">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-950/80 border-b border-slate-800 text-slate-400 font-mono text-[11px] uppercase">
                    <tr>
                      <th className="py-3 px-3.5">#</th>
                      <th className="py-3 px-3.5">Device ID</th>
                      <th className="py-3 px-3.5">Timestamp</th>
                      <th className="py-3 px-3.5">Coords</th>
                      {isWrongSide && <th className="py-3 px-3.5">Progression</th>}
                      {isWrongSide && <th className="py-3 px-3.5">Reason / Note</th>}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 font-sans">
                    {incident.observations.map((obs, idx) => {
                      const isRejected = obs.wrong_way_status === 'rejected';
                      const isConfirmed = obs.wrong_way_status === 'confirmed';

                      return (
                        <tr 
                          key={obs.id || obs.event_nonce || idx} 
                          className={`hover:bg-slate-800/40 transition-colors ${
                            isRejected ? 'bg-rose-950/20' : ''
                          }`}
                        >
                          <td className="py-3 px-3.5 font-bold font-mono text-slate-300">
                            {idx + 1}
                          </td>
                          <td className="py-3 px-3.5 font-mono text-blue-400 font-medium">
                            {obs.device_id}
                          </td>
                          <td className="py-3 px-3.5 font-mono text-slate-300 whitespace-nowrap">
                            {new Date(obs.ts).toLocaleTimeString()}
                          </td>
                          <td className="py-3 px-3.5 font-mono text-slate-400 text-[11px]">
                            {obs.lat.toFixed(5)}, {obs.lon.toFixed(5)}
                          </td>
                          {isWrongSide && (
                            <td className="py-3 px-3.5">
                              {obs.wrong_way_status ? (
                                <span
                                  className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono capitalize ${
                                    isConfirmed
                                      ? 'bg-emerald-950 text-emerald-300 border border-emerald-800/50'
                                      : isRejected
                                      ? 'bg-rose-950 text-rose-300 border border-rose-800/50'
                                      : 'bg-sky-950 text-sky-300 border border-sky-800/50'
                                  }`}
                                >
                                  {obs.wrong_way_status}
                                </span>
                              ) : (
                                <span className="text-slate-500">—</span>
                              )}
                            </td>
                          )}
                          {isWrongSide && (
                            <td className="py-3 px-3.5 text-slate-300 text-[11px]">
                              {obs.rejection_reason ? (
                                <span className="text-rose-300 font-mono bg-rose-950/60 px-1.5 py-0.5 rounded border border-rose-800/40">
                                  {obs.rejection_reason}
                                </span>
                              ) : isConfirmed ? (
                                <span className="text-emerald-400 text-[11px]">Valid vector</span>
                              ) : (
                                <span className="text-slate-500">Awaiting vector</span>
                              )}
                            </td>
                          )}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>

        {/* Right 5 Columns: Video Evidence Player & Metadata Card */}
        <div className="lg:col-span-5 space-y-6">
          {/* Evidence Video Section */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wider flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-blue-400" />
                <span>Video Evidence Clip</span>
              </h2>
              <span className="text-xs text-slate-400 font-mono">
                {incident.evidence_items.length} clips
              </span>
            </div>

            <EvidencePlayer evidenceItems={incident.evidence_items} />
          </div>

          {/* Incident Telemetry Summary Card */}
          <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 space-y-4 shadow-xl">
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider border-b border-slate-800 pb-3">
              Incident Metadata & Cryptographic Boundary
            </h3>

            <div className="space-y-3 text-xs">
              <div className="flex items-center justify-between py-1 border-b border-slate-800/50">
                <span className="text-slate-400">Violation Type:</span>
                <span className="font-semibold text-slate-200 uppercase font-mono">
                  {incident.violation_type}
                </span>
              </div>

              <div className="flex items-center justify-between py-1 border-b border-slate-800/50">
                <span className="text-slate-400">Window Start:</span>
                <span className="font-mono text-slate-200">
                  {new Date(incident.window_start).toLocaleString()}
                </span>
              </div>

              <div className="flex items-center justify-between py-1 border-b border-slate-800/50">
                <span className="text-slate-400">Window End:</span>
                <span className="font-mono text-slate-200">
                  {new Date(incident.window_end).toLocaleString()}
                </span>
              </div>

              <div className="py-2 space-y-1">
                <div className="text-slate-400 flex items-center gap-1.5">
                  <Fingerprint className="w-3.5 h-3.5 text-blue-400" />
                  <span>HMAC-SHA256 Hashed Plate:</span>
                </div>
                <div className="p-2 rounded-lg bg-slate-950 border border-slate-800 font-mono text-[11px] text-blue-300 break-all select-all">
                  {incident.hashed_plate}
                </div>
                <div className="text-[10px] text-slate-400 italic">
                  Raw plate discarded at boundary. Plaintext never persisted.
                </div>
              </div>

              {/* Review Audit Info */}
              {isReviewed && (
                <div className="p-3 rounded-xl bg-purple-950/30 border border-purple-500/30 space-y-1 mt-2">
                  <div className="text-purple-300 font-semibold text-xs flex items-center gap-1">
                    <UserCheck className="w-3.5 h-3.5" />
                    <span>Audit Trail Log</span>
                  </div>
                  <div className="text-slate-300 text-[11px]">
                    Reviewed by: <strong className="text-white">{incident.reviewer_email || incident.reviewed_by}</strong>
                  </div>
                  <div className="text-slate-400 text-[10px] font-mono">
                    Timestamp: {incident.reviewed_at ? new Date(incident.reviewed_at).toISOString() : ''}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
