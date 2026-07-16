import { Ban, CheckCircle2, CircleDashed, Star } from "lucide-react";
import type { VerificationStatus } from "../types/radar";

const styles: Record<VerificationStatus, string> = {
  verified: "border-brand/20 bg-brand-soft text-brand",
  unverified: "border-warning/20 bg-warning-soft text-warning",
  excluded: "border-line bg-surface-muted text-excluded",
};

const labels: Record<VerificationStatus, string> = {
  verified: "已校验",
  unverified: "待确认",
  excluded: "已排除",
};

const icons = {
  verified: CheckCircle2,
  unverified: CircleDashed,
  excluded: Ban,
};

interface StatusBadgeProps {
  status: VerificationStatus;
  watchlist?: boolean;
}

export function StatusBadge({ status, watchlist = false }: StatusBadgeProps) {
  const Icon = watchlist ? Star : icons[status];
  const label = watchlist ? "Watchlist" : labels[status];
  const color = watchlist ? "border-info/20 bg-info-soft text-info" : styles[status];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold ${color}`}
    >
      <Icon className="size-3.5" aria-hidden="true" />
      {label}
    </span>
  );
}
