import { ChevronDown } from "lucide-react";
import type {
  FeatureScore,
  ScoredRadarCandidate,
  StockFeatureBreakdown,
} from "../types/radar";

const tierLabels = {
  pro: "Pro 深度分析",
  flash: "Flash 简报",
  deterministic: "规则摘要",
  not_applicable: "不适用",
};

const featureLabels: Record<string, string> = {
  directness: "关系直接度",
  exposure: "业务暴露",
  economic_scale: "经济量级",
  duration: "持续时间",
  sensitivity: "经营敏感度",
};

export function ImpactCandidate({ candidate }: { candidate: ScoredRadarCandidate }) {
  const positiveFeatures = featureEntries(candidate.feature_breakdown.positive);
  const negativeFeatures = featureEntries(candidate.feature_breakdown.negative);
  return (
    <details className="group border-b border-line last:border-0">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 py-3">
        <div>
          <p className="text-sm font-semibold">
            {candidate.name} <span className="text-xs font-normal text-ink-muted">{candidate.symbol}</span>
          </p>
          <p className="mt-1 text-[11px] text-ink-muted">
            {tierLabels[candidate.analysis_tier]} · 置信度 {candidate.confidence}
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs font-semibold tabular-nums">
          <span className="text-brand">正向 {candidate.positive_magnitude}</span>
          <span className="text-risk">负向 {candidate.negative_magnitude}</span>
          <ChevronDown className="size-4 text-ink-muted transition group-open:rotate-180" />
        </div>
      </summary>
      <div className="grid gap-3 pb-3 sm:grid-cols-2">
        <FeatureSection title="正向特征" features={positiveFeatures} />
        <FeatureSection title="负向特征" features={negativeFeatures} />
      </div>
    </details>
  );
}

function FeatureSection({ title, features }: { title: string; features: [string, FeatureScore][] }) {
  return (
    <div>
      <p className="mb-2 text-[11px] font-semibold text-ink-muted">{title}</p>
      <div className="space-y-2">
        {features.length === 0 && <p className="rounded-lg bg-canvas px-3 py-2 text-xs text-ink-muted">暂无</p>}
        {features.map(([name, feature]) => (
          <div key={name} className="rounded-lg bg-canvas px-3 py-2 text-xs">
            <div className="flex justify-between gap-2">
              <span>{featureLabels[name] ?? name}</span><strong>{feature.value}</strong>
            </div>
            <p className="mt-1 break-all text-[10px] text-ink-muted">
              {feature.reason_codes.join(" / ")}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

function featureEntries(value?: StockFeatureBreakdown): [string, FeatureScore][] {
  return Object.entries(value ?? {}).filter(
    (entry): entry is [string, FeatureScore] => entry[1] !== undefined,
  );
}
