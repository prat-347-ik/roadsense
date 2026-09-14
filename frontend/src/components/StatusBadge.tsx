import React from 'react';
import { IncidentStatus } from '../types/api';
import { 
  CheckCircle2, 
  XCircle, 
  AlertTriangle, 
  Clock, 
  ShieldCheck, 
  AlertCircle 
} from 'lucide-react';

interface StatusBadgeProps {
  status: IncidentStatus | string;
  size?: 'sm' | 'md' | 'lg';
  showIcon?: boolean;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ 
  status, 
  size = 'md', 
  showIcon = true 
}) => {
  const getBadgeConfig = (st: string) => {
    switch (st) {
      case 'corroborated':
        return {
          label: 'Ready for Review',
          subLabel: 'Corroborated',
          bg: 'bg-emerald-950/80 border-emerald-500/40 text-emerald-300',
          dot: 'bg-emerald-400',
          icon: ShieldCheck,
        };
      case 'corroborated_no_evidence':
        return {
          label: 'Missing Evidence',
          subLabel: 'TTL Expired',
          bg: 'bg-amber-950/80 border-amber-500/50 text-amber-300',
          dot: 'bg-amber-400',
          icon: AlertTriangle,
        };
      case 'rejected':
        return {
          label: 'Rejected',
          subLabel: 'Dismissed',
          bg: 'bg-rose-950/80 border-rose-500/40 text-rose-300',
          dot: 'bg-rose-400',
          icon: XCircle,
        };
      case 'confirmed':
        return {
          label: 'Confirmed',
          subLabel: 'Approved',
          bg: 'bg-purple-950/80 border-purple-500/40 text-purple-300',
          dot: 'bg-purple-400',
          icon: CheckCircle2,
        };
      case 'candidate':
      default:
        return {
          label: 'Candidate',
          subLabel: 'Awaiting Corroboration',
          bg: 'bg-sky-950/80 border-sky-500/40 text-sky-300',
          dot: 'bg-sky-400',
          icon: Clock,
        };
    }
  };

  const config = getBadgeConfig(status);
  const Icon = config.icon;

  const sizeClasses = {
    sm: 'text-xs px-2 py-0.5 gap-1',
    md: 'text-xs px-2.5 py-1 gap-1.5 font-medium',
    lg: 'text-sm px-3 py-1.5 gap-2 font-medium',
  };

  const iconSizes = {
    sm: 'w-3 h-3',
    md: 'w-3.5 h-3.5',
    lg: 'w-4 h-4',
  };

  return (
    <span 
      className={`inline-flex items-center rounded-full border shadow-sm backdrop-blur-sm ${config.bg} ${sizeClasses[size]}`}
    >
      {showIcon && <Icon className={`${iconSizes[size]} shrink-0`} />}
      <span>{config.label}</span>
    </span>
  );
};
