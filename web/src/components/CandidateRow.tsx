import { ChevronRight, ShieldAlert, Star } from "lucide-react";
import type { ImpactStrength, RadarCandidate, ScoredRadarCandidate } from "../types/radar";
import { ImpactBadge } from "./ImpactBadge";
import { StatusBadge } from "./StatusBadge";

interface CandidateRowProps {
  candidate: RadarCandidate | ScoredRadarCandidate;
  compact?: boolean;
}

const impactTypeLabels: Record<string, string> = {
  direct: "直接影响",
  indirect: "间接影响",
  sentiment: "情绪映射",
  negative: "负面影响",
  false_positive: "误匹配",
};

const impactStrengthLabels: Record<ImpactStrength, string> = {
  high: "高强度",
  medium: "中强度",
  low: "低强度",
  unknown: "强度未知",
};

export function CandidateRow({ candidate, compact = false }: CandidateRowProps) {
  const scored = "positive_magnitude" in candidate;
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
            <span>{impactTypeLabels[candidate.impact_type] ?? candidate.impact_type} / {impactStrengthLabels[candidate.impact_strength]}</span>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <ImpactBadge kind="direction" value={candidate.impact_direction} />
            {scored ? (
              <>
                <span className="rounded-full bg-brand-soft px-2.5 py-1 text-[11px] font-semibold text-brand">正向 {candidate.positive_magnitude}</span>
                <span className="rounded-full bg-risk-soft px-2.5 py-1 text-[11px] font-semibold text-risk">负向 {candidate.negative_magnitude}</span>
              </>
            ) : <ImpactBadge kind="score" value={candidate.impact_score} />}
            {typeof candidate.confidence === "number"
              ? <span className="rounded-full border border-info/20 bg-info-soft px-2.5 py-1 text-[11px] font-semibold text-info">置信度：{candidate.confidence}</span>
              : <ImpactBadge kind="confidence" value={candidate.confidence} />}
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
