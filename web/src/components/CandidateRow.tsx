import { ChevronRight, ShieldAlert, Star } from "lucide-react";
import type { RadarCandidate } from "../types/radar";
import { StatusBadge } from "./StatusBadge";

interface CandidateRowProps {
  candidate: RadarCandidate;
  compact?: boolean;
}

export function CandidateRow({ candidate, compact = false }: CandidateRowProps) {
  return (
    <details className="group border-b border-line last:border-b-0">
      <summary className="flex cursor-pointer list-none items-start gap-3 py-3.5">
        <div className="grid size-8 shrink-0 place-items-center rounded-lg bg-canvas text-xs font-bold text-brand">
          {candidate.name.slice(0, 1)}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-semibold text-ink">{candidate.name}</p>
            {candidate.watchlist_hit && <Star className="size-3.5 fill-info-soft text-info" aria-label="Watchlist 命中" />}
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-ink-muted">
            <span className="font-medium tabular-nums">{candidate.symbol}</span>
            <span>·</span>
            <span>{candidate.impact_type} / {candidate.impact_strength}</span>
          </div>
        </div>
        <ChevronRight className="mt-2 size-4 shrink-0 text-ink-muted transition group-open:rotate-90" aria-hidden="true" />
      </summary>
      {!compact && (
        <div className="pb-4 pl-11 text-xs leading-5 text-ink-muted">
          <div className="flex flex-wrap gap-2">
            <StatusBadge status={candidate.verification_status} />
            {candidate.watchlist_hit && <StatusBadge status={candidate.verification_status} watchlist />}
          </div>
          <p className="mt-3">{candidate.reasoning || "暂无研究理由"}</p>
          {candidate.verification_source && <p className="mt-2 text-brand">证据源：{candidate.verification_source}</p>}
          {candidate.risks.length > 0 && (
            <div className="mt-3 flex gap-2 rounded-lg bg-risk-soft px-3 py-2 text-risk">
              <ShieldAlert className="mt-0.5 size-3.5 shrink-0" />
              <span>{candidate.risks.join("；")}</span>
            </div>
          )}
        </div>
      )}
    </details>
  );
}
