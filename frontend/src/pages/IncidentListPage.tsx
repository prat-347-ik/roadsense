import React, { useState, useEffect, useMemo } from 'react';
import { api } from '../services/api';
import { IncidentStatus, IncidentSummary, ViolationType } from '../types/api';
import { StatusBadge } from '../components/StatusBadge';
import { 
  Filter, 
  Search, 
  RefreshCw, 
  AlertCircle, 
  ShieldCheck, 
  Clock, 
  XCircle, 
  CheckCircle2, 
  ChevronRight, 
  Car, 
  TrafficCone,
  Layers,
  FileQuestion
} from 'lucide-react';

interface IncidentListPageProps {
  onSelectIncident: (id: number) => void;
}

export const IncidentListPage: React.FC<IncidentListPageProps> = ({ onSelectIncident }) => {
  const [incidents, setIncidents] = useState<IncidentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');

  const fetchIncidents = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getIncidents({
        status: statusFilter !== 'all' ? (statusFilter as IncidentStatus) : undefined,
        violation_type: typeFilter !== 'all' ? (typeFilter as ViolationType) : undefined,
        limit: 100,
      });
      setIncidents(data);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch incident queue');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchIncidents();
  }, [statusFilter, typeFilter]);

  // Client-side search filtering by hashed plate or ID
  const filteredIncidents = useMemo(() => {
    if (!searchQuery.trim()) return incidents;
    const q = searchQuery.toLowerCase().trim();
    return incidents.filter(
      (inc) =>
        inc.id.toString().includes(q) ||
        inc.hashed_plate.toLowerCase().includes(q) ||
        inc.violation_type.toLowerCase().includes(q)
    );
  }, [incidents, searchQuery]);

  // Count summaries for status cards
  const stats = useMemo(() => {
    const corroboratedCount = incidents.filter((i) => i.status === 'corroborated').length;
    const noEvidenceCount = incidents.filter((i) => i.status === 'corroborated_no_evidence').length;
    const rejectedCount = incidents.filter((i) => i.status === 'rejected').length;
    const candidateCount = incidents.filter((i) => i.status === 'candidate').length;
    const confirmedCount = incidents.filter((i) => i.status === 'confirmed').length;

    return {
      total: incidents.length,
      corroborated: corroboratedCount,
      noEvidence: noEvidenceCount,
      rejected: rejectedCount,
      candidate: candidateCount,
      confirmed: confirmedCount,
    };
  }, [incidents]);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
            Incident Review Queue
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Corroborated vehicle infractions requiring human evidentiary verification
          </p>
        </div>

        <button
          onClick={fetchIncidents}
          disabled={loading}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs font-semibold shadow-sm transition-all disabled:opacity-50 self-start sm:self-auto"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-blue-400' : ''}`} />
          <span>Refresh Queue</span>
        </button>
      </div>

      {/* Stats KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <div 
          onClick={() => setStatusFilter(statusFilter === 'corroborated' ? 'all' : 'corroborated')}
          className={`cursor-pointer p-4 rounded-xl border transition-all ${
            statusFilter === 'corroborated'
              ? 'bg-emerald-950/60 border-emerald-500/60 ring-2 ring-emerald-500/30'
              : 'bg-slate-900/60 border-slate-800 hover:border-slate-700'
          }`}
        >
          <div className="flex items-center justify-between text-emerald-400 mb-1">
            <span className="text-xs font-semibold uppercase tracking-wider">Ready for Review</span>
            <ShieldCheck className="w-4 h-4" />
          </div>
          <div className="text-2xl font-bold text-white font-mono">{stats.corroborated}</div>
          <div className="text-[11px] text-slate-400 mt-0.5">Corroborated & clips pending</div>
        </div>

        <div 
          onClick={() => setStatusFilter(statusFilter === 'corroborated_no_evidence' ? 'all' : 'corroborated_no_evidence')}
          className={`cursor-pointer p-4 rounded-xl border transition-all ${
            statusFilter === 'corroborated_no_evidence'
              ? 'bg-amber-950/60 border-amber-500/60 ring-2 ring-amber-500/30'
              : 'bg-slate-900/60 border-slate-800 hover:border-slate-700'
          }`}
        >
          <div className="flex items-center justify-between text-amber-400 mb-1">
            <span className="text-xs font-semibold uppercase tracking-wider">Missing Evidence</span>
            <FileQuestion className="w-4 h-4" />
          </div>
          <div className="text-2xl font-bold text-white font-mono">{stats.noEvidence}</div>
          <div className="text-[11px] text-slate-400 mt-0.5">TTL expired without clips</div>
        </div>

        <div 
          onClick={() => setStatusFilter(statusFilter === 'rejected' ? 'all' : 'rejected')}
          className={`cursor-pointer p-4 rounded-xl border transition-all ${
            statusFilter === 'rejected'
              ? 'bg-rose-950/60 border-rose-500/60 ring-2 ring-rose-500/30'
              : 'bg-slate-900/60 border-slate-800 hover:border-slate-700'
          }`}
        >
          <div className="flex items-center justify-between text-rose-400 mb-1">
            <span className="text-xs font-semibold uppercase tracking-wider">Rejected</span>
            <XCircle className="w-4 h-4" />
          </div>
          <div className="text-2xl font-bold text-white font-mono">{stats.rejected}</div>
          <div className="text-[11px] text-slate-400 mt-0.5">Auto-filter or dismissed</div>
        </div>

        <div 
          onClick={() => setStatusFilter(statusFilter === 'candidate' ? 'all' : 'candidate')}
          className={`cursor-pointer p-4 rounded-xl border transition-all ${
            statusFilter === 'candidate'
              ? 'bg-sky-950/60 border-sky-500/60 ring-2 ring-sky-500/30'
              : 'bg-slate-900/60 border-slate-800 hover:border-slate-700'
          }`}
        >
          <div className="flex items-center justify-between text-sky-400 mb-1">
            <span className="text-xs font-semibold uppercase tracking-wider">Candidate</span>
            <Clock className="w-4 h-4" />
          </div>
          <div className="text-2xl font-bold text-white font-mono">{stats.candidate}</div>
          <div className="text-[11px] text-slate-400 mt-0.5">Awaiting corroboration</div>
        </div>

        <div 
          onClick={() => setStatusFilter(statusFilter === 'confirmed' ? 'all' : 'confirmed')}
          className={`cursor-pointer p-4 rounded-xl border transition-all ${
            statusFilter === 'confirmed'
              ? 'bg-purple-950/60 border-purple-500/60 ring-2 ring-purple-500/30'
              : 'bg-slate-900/60 border-slate-800 hover:border-slate-700'
          }`}
        >
          <div className="flex items-center justify-between text-purple-400 mb-1">
            <span className="text-xs font-semibold uppercase tracking-wider">Confirmed</span>
            <CheckCircle2 className="w-4 h-4" />
          </div>
          <div className="text-2xl font-bold text-white font-mono">{stats.confirmed}</div>
          <div className="text-[11px] text-slate-400 mt-0.5">Human approved</div>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-4 flex flex-col md:flex-row gap-4 items-stretch md:items-center justify-between">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-400 uppercase tracking-wider">
            <Filter className="w-3.5 h-3.5 text-blue-400" />
            <span>Filters:</span>
          </div>

          {/* Status Dropdown */}
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-1.5 rounded-xl bg-slate-950 border border-slate-700 text-xs text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="all">All Statuses</option>
            <option value="corroborated">Ready for Review (corroborated)</option>
            <option value="corroborated_no_evidence">Missing Evidence (TTL Expired)</option>
            <option value="rejected">Rejected (Auto & Human)</option>
            <option value="candidate">Candidate (Pending Corroboration)</option>
            <option value="confirmed">Confirmed (Approved)</option>
          </select>

          {/* Violation Type Dropdown */}
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className="px-3 py-1.5 rounded-xl bg-slate-950 border border-slate-700 text-xs text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="all">All Violation Types</option>
            <option value="wrong_side">Wrong-Side Driving</option>
            <option value="red_light">Red-Light Infraction</option>
          </select>
        </div>

        {/* Search input */}
        <div className="relative min-w-[240px]">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by ID, plate hash..."
            className="w-full pl-9 pr-4 py-1.5 bg-slate-950 border border-slate-700 rounded-xl text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="rounded-xl bg-rose-950/60 border border-rose-500/40 p-4 flex items-center justify-between text-rose-200 text-sm">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-5 h-5 text-rose-400 shrink-0" />
            <span>{error}</span>
          </div>
          <button
            onClick={fetchIncidents}
            className="px-3 py-1 rounded-lg bg-rose-900/60 hover:bg-rose-800 text-rose-200 text-xs font-semibold"
          >
            Retry
          </button>
        </div>
      )}

      {/* Incidents Table / List */}
      <div className="bg-slate-900/60 border border-slate-800 rounded-2xl overflow-hidden shadow-xl">
        {loading ? (
          <div className="p-12 text-center space-y-3">
            <div className="w-8 h-8 border-2 border-blue-500/30 border-t-blue-500 rounded-full animate-spin mx-auto"></div>
            <div className="text-sm text-slate-400 font-medium">Loading incident telemetry queue...</div>
          </div>
        ) : filteredIncidents.length === 0 ? (
          <div className="p-12 text-center space-y-3">
            <Layers className="w-10 h-10 text-slate-600 mx-auto" />
            <div className="text-base font-semibold text-slate-300">No Incidents Found</div>
            <p className="text-xs text-slate-500 max-w-sm mx-auto">
              No clustered violation candidates match the current filter criteria. Run synthetic bursts script to generate test data.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-slate-800/80">
            {filteredIncidents.map((incident) => {
              const isWrongSide = incident.violation_type === 'wrong_side';
              const isReviewed = incident.reviewed_by !== null;

              return (
                <div
                  key={incident.id}
                  onClick={() => onSelectIncident(incident.id)}
                  className="p-4 sm:p-5 hover:bg-slate-800/50 cursor-pointer transition-colors flex flex-col sm:flex-row sm:items-center justify-between gap-4 group"
                >
                  <div className="flex items-start gap-4">
                    {/* Icon Badge */}
                    <div
                      className={`p-3 rounded-xl border shrink-0 ${
                        isWrongSide
                          ? 'bg-orange-950/40 border-orange-500/30 text-orange-400'
                          : 'bg-red-950/40 border-red-500/30 text-red-400'
                      }`}
                    >
                      {isWrongSide ? (
                        <Car className="w-5 h-5" />
                      ) : (
                        <TrafficCone className="w-5 h-5" />
                      )}
                    </div>

                    <div className="space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-bold text-white text-base">
                          Incident #{incident.id}
                        </span>
                        <span className="text-xs uppercase px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-slate-300 font-mono font-medium">
                          {incident.violation_type === 'wrong_side' ? 'Wrong-Side' : 'Red-Light'}
                        </span>
                        <StatusBadge status={incident.status} size="sm" />
                      </div>

                      {/* Hashed Plate */}
                      <div className="text-xs text-slate-400 flex items-center gap-2 font-mono">
                        <span className="text-slate-500">Plate Hash:</span>
                        <span className="text-slate-300 bg-black/40 px-2 py-0.5 rounded text-[11px]">
                          {incident.hashed_plate.slice(0, 16)}...
                        </span>
                      </div>

                      {/* Time Window & Sensors */}
                      <div className="text-xs text-slate-400 flex flex-wrap items-center gap-x-4 gap-y-1 pt-1">
                        <span>
                          Sensors / Bursts:{' '}
                          <strong className="text-slate-200 font-mono">
                            {incident.observation_count}
                          </strong>
                        </span>
                        <span>
                          Time:{' '}
                          <span className="text-slate-200 font-mono">
                            {new Date(incident.window_start).toLocaleTimeString()} —{' '}
                            {new Date(incident.window_end).toLocaleTimeString()}
                          </span>
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Right side: Review audit or call to action */}
                  <div className="flex items-center justify-between sm:justify-end gap-4 self-end sm:self-center shrink-0">
                    {isReviewed ? (
                      <div className="text-right text-xs space-y-0.5">
                        <div className="text-purple-300 font-medium flex items-center gap-1 justify-end">
                          <CheckCircle2 className="w-3.5 h-3.5 text-purple-400" />
                          <span>Reviewed</span>
                        </div>
                        <div className="text-[11px] text-slate-500 font-mono">
                          {incident.reviewed_at ? new Date(incident.reviewed_at).toLocaleDateString() : ''}
                        </div>
                      </div>
                    ) : incident.status === 'corroborated' ? (
                      <span className="text-xs font-semibold px-3 py-1.5 rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 group-hover:bg-emerald-500/20 transition-colors">
                        Review Now &rarr;
                      </span>
                    ) : null}

                    <div className="w-8 h-8 rounded-full bg-slate-800 flex items-center justify-center text-slate-400 group-hover:text-white group-hover:bg-blue-600 transition-all">
                      <ChevronRight className="w-4 h-4" />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
