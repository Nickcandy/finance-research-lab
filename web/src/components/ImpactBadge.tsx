import type { ConfidenceLevel, ImpactDirection } from "../types/radar";

type ImpactBadgeProps =
  | { kind: "direction"; value: ImpactDirection; label?: string }
  | { kind: "score"; value: number | null; label?: string }
  | { kind: "confidence"; value: ConfidenceLevel; label?: string };

const directionLabels: Record<ImpactDirection, string> = {
  positive: "利好",
  negative: "利空",
  mixed: "多空混合",
  neutral: "中性",
  unknown: "未知",
};

const confidenceLabels: Record<ConfidenceLevel, string> = {
  high: "高",
  medium: "中",
  low: "低",
  unknown: "未知",
};

const directionStyles: Record<ImpactDirection, string> = {
  positive: "border-brand/20 bg-brand-soft text-brand",
  negative: "border-risk/20 bg-risk-soft text-risk",
  mixed: "border-warning/20 bg-warning-soft text-warning",
  neutral: "border-info/20 bg-info-soft text-info",
  unknown: "border-line bg-surface-muted text-excluded",
};

export function ImpactBadge(props: ImpactBadgeProps) {
  const label = props.label ?? (props.kind === "confidence" ? "置信度" : props.kind === "score" ? "指数" : "方向");
  const value = props.kind === "direction"
    ? directionLabels[props.value]
    : props.kind === "confidence"
      ? confidenceLabels[props.value]
      : formatScore(props.value);
  const style = props.kind === "direction"
    ? directionStyles[props.value]
    : props.kind === "score"
      ? scoreStyle(props.value)
      : props.value === "high"
        ? directionStyles.positive
        : props.value === "low"
          ? directionStyles.mixed
          : props.value === "medium"
            ? directionStyles.neutral
            : directionStyles.unknown;

  return <span className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${style}`}>{label}：{value}</span>;
}

function formatScore(score: number | null) {
  if (score === null) return "待评估";
  return score > 0 ? `+${score}` : String(score);
}

function scoreStyle(score: number | null) {
  if (score === null) return directionStyles.unknown;
  if (score > 0) return directionStyles.positive;
  if (score < 0) return directionStyles.negative;
  return directionStyles.neutral;
}
