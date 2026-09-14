import React, { useState } from 'react';
import { EvidenceItem } from '../types/api';
import { Video, Download, CheckCircle2, Clock, Film, ExternalLink } from 'lucide-react';

interface EvidencePlayerProps {
  evidenceItems: EvidenceItem[];
}

export const EvidencePlayer: React.FC<EvidencePlayerProps> = ({ evidenceItems }) => {
  const [selectedNonce, setSelectedNonce] = useState<string>(
    evidenceItems[0]?.event_nonce || ''
  );

  if (evidenceItems.length === 0) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-6 text-center space-y-2">
        <Film className="w-8 h-8 text-slate-600 mx-auto" />
        <div className="text-sm font-medium text-slate-300">No Evidence Clips Attached</div>
        <p className="text-xs text-slate-500 max-w-sm mx-auto">
          No video or image evidence was uploaded by reporting edge devices for this incident.
        </p>
      </div>
    );
  }

  const activeItem = evidenceItems.find(item => item.event_nonce === selectedNonce) || evidenceItems[0];

  return (
    <div className="space-y-4">
      {/* Evidence Clip Tabs if multiple */}
      {evidenceItems.length > 1 && (
        <div className="flex items-center gap-2 overflow-x-auto pb-1">
          {evidenceItems.map((item, idx) => {
            const isSelected = item.event_nonce === selectedNonce;
            const isUploaded = !!item.uploaded_at;

            return (
              <button
                key={item.event_nonce}
                onClick={() => setSelectedNonce(item.event_nonce)}
                className={`px-3 py-2 rounded-lg text-xs font-medium border flex items-center gap-2 whitespace-nowrap transition-all ${
                  isSelected
                    ? 'bg-blue-600/20 border-blue-500 text-blue-300 shadow-md shadow-blue-500/10'
                    : 'bg-slate-900/60 border-slate-800 text-slate-400 hover:bg-slate-800 hover:text-slate-200'
                }`}
              >
                <Video className="w-3.5 h-3.5" />
                <span>Camera {idx + 1} ({item.device_id})</span>
                {isUploaded ? (
                  <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
                ) : (
                  <span className="w-2 h-2 rounded-full bg-amber-400"></span>
                )}
              </button>
            );
          })}
        </div>
      )}

      {/* Main Video Player Container */}
      <div className="rounded-xl border border-slate-800 bg-slate-950 overflow-hidden shadow-xl">
        <div className="relative aspect-video bg-black flex items-center justify-center">
          {activeItem?.view_url ? (
            <video
              key={activeItem.view_url}
              controls
              autoPlay={false}
              className="w-full h-full object-contain"
              poster=""
            >
              <source src={activeItem.view_url} type="video/mp4" />
              Your browser does not support HTML5 video streaming.
            </video>
          ) : (
            <div className="text-center p-8 space-y-3">
              <Clock className="w-10 h-10 text-amber-500/60 mx-auto animate-pulse" />
              <div className="text-sm font-semibold text-amber-300">
                Evidence Clip Pending / Expired
              </div>
              <p className="text-xs text-slate-400 max-w-xs mx-auto">
                Evidence was requested from <code className="text-blue-300">{activeItem?.device_id}</code> but has not been uploaded.
              </p>
            </div>
          )}
        </div>

        {/* Video Metadata Footer */}
        <div className="p-4 bg-slate-900/90 border-t border-slate-800 flex flex-wrap items-center justify-between gap-3 text-xs">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-slate-200">Device ID:</span>
              <span className="font-mono text-blue-400">{activeItem?.device_id}</span>
              {activeItem?.uploaded_at ? (
                <span className="inline-flex items-center gap-1 text-[11px] text-emerald-400 bg-emerald-950/60 px-2 py-0.5 rounded border border-emerald-800/40 font-mono">
                  <CheckCircle2 className="w-3 h-3" /> Uploaded
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 text-[11px] text-amber-400 bg-amber-950/60 px-2 py-0.5 rounded border border-amber-800/40 font-mono">
                  <Clock className="w-3 h-3" /> Awaiting Upload
                </span>
              )}
            </div>
            <div className="text-slate-400 font-mono text-[11px] break-all">
              Event Nonce: {activeItem?.event_nonce}
            </div>
          </div>

          {activeItem?.view_url && (
            <div className="flex items-center gap-2">
              <a
                href={activeItem.view_url}
                target="_blank"
                rel="noreferrer"
                download={`evidence-${activeItem.event_nonce}.mp4`}
                className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 flex items-center gap-1.5 transition-colors font-medium text-xs"
              >
                <Download className="w-3.5 h-3.5 text-blue-400" />
                <span>Download Clip</span>
              </a>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
