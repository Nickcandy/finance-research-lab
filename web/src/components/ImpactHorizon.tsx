import type { DirectionalHorizons, HorizonCategory, ImpactHorizon } from "../types/radar";

const categoryLabels: Record<HorizonCategory, string> = {
  immediate: "即时",
  short: "短期",
  medium: "中期",
  long: "长期",
  structural: "结构性",
  unknown: "待验证",
};

interface HorizonBadgesProps {
  positive: DirectionalHorizons | null;
  negative: DirectionalHorizons | null;
}

export function HorizonBadges({ positive, negative }: HorizonBadgesProps) {
  return (
    <>
      {positive && <HorizonBadge label="正向周期" horizon={positive.fundamental} positive />}
      {negative && <HorizonBadge label="负向周期" horizon={negative.fundamental} />}
    </>
  );
}

export function HorizonDetails({ positive, negative }: HorizonBadgesProps) {
  if (!positive && !negative) {
    return <p className="mt-3 text-xs text-ink-muted">影响周期待验证</p>;
  }
  return (
    <div className="mt-3 grid gap-2 sm:grid-cols-2">
      {positive && <HorizonCard title="正向影响周期" horizons={positive} positive />}
      {negative && <HorizonCard title="负向影响周期" horizons={negative} />}
    </div>
  );
}

function HorizonBadge({ label, horizon, positive = false }: { label: string; horizon: ImpactHorizon; positive?: boolean }) {
  return (
    <span className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${
      positive ? "border-brand/20 bg-brand-soft text-brand" : "border-risk/20 bg-risk-soft text-risk"
    }`}>
      {label}：{categoryLabels[horizon.category]}
    </span>
  );
}

function HorizonCard({ title, horizons, positive = false }: { title: string; horizons: DirectionalHorizons; positive?: boolean }) {
  return (
    <div className={`rounded-lg border px-3 py-3 ${positive ? "border-brand/15 bg-brand-soft/40" : "border-risk/15 bg-risk-soft/40"}`}>
      <p className="font-semibold text-ink">{title}</p>
      <p className="mt-1">市场反应：{formatHorizon(horizons.market)}</p>
      <p>市场层置信度：{confidenceLabel(horizons.market.confidence)}</p>
      <p>市场层依据：{horizons.market.basis.join("；")}</p>
      <p>市场层失效条件：{horizons.market.invalidation_conditions.join("；")}</p>
      <p>基本面兑现：{formatHorizon(horizons.fundamental)}</p>
      <p>基本面层置信度：{confidenceLabel(horizons.fundamental.confidence)}</p>
      <p>基本面层依据：{horizons.fundamental.basis.join("；")}</p>
      <p>基本面层失效条件：{horizons.fundamental.invalidation_conditions.join("；")}</p>
    </div>
  );
}

function formatHorizon(horizon: ImpactHorizon) {
  if (horizon.category === "unknown") return "待验证";
  const unit = horizon.unit === "trading_day" ? "个交易日" : "个月";
  const duration = horizon.max_duration === null
    ? `${horizon.min_duration}${unit}以上`
    : horizon.min_duration === horizon.max_duration
      ? `${horizon.min_duration}${unit}`
      : `${horizon.min_duration}～${horizon.max_duration}${unit}`;
  return `${categoryLabels[horizon.category]}（${duration}）`;
}

function confidenceLabel(value: ImpactHorizon["confidence"]) {
  return { high: "高", medium: "中", low: "低", unknown: "未知" }[value];
}
