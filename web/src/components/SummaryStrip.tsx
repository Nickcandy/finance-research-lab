import { CheckCircle2, CircleDashed, Newspaper, RadioTower } from "lucide-react";
import type { RadarSummary } from "../types/radar";

interface SummaryStripProps {
  summary: RadarSummary;
}

export function SummaryStrip({ summary }: SummaryStripProps) {
  const items = [
    { label: "聚类事件", value: summary.total_event_count, note: `核心 ${summary.core_event_count}`, icon: Newspaper, color: "text-brand" },
    { label: "已校验", value: summary.verified_count, note: "证据齐全", icon: CheckCircle2, color: "text-brand" },
    { label: "待确认", value: summary.unverified_count, note: "需要补证据", icon: CircleDashed, color: "text-warning" },
    { label: "独立来源", value: summary.source_count, note: "跨事件去重", icon: RadioTower, color: "text-info" },
  ];
  return (
    <section className="grid grid-cols-2 overflow-hidden rounded-xl border border-line bg-surface lg:grid-cols-4" aria-label="日报摘要">
      {items.map(({ label, value, note, icon: Icon, color }, index) => (
        <div
          key={label}
          className={`p-4 sm:p-5 ${index % 2 === 0 ? "border-r border-line" : ""} ${index < 2 ? "border-b border-line lg:border-b-0" : ""} ${index === 1 ? "lg:border-r" : ""}`}
        >
          <div className="flex items-center justify-between gap-3">
            <p className="text-xs font-medium text-ink-muted">{label}</p>
            <Icon className={`size-4 ${color}`} aria-hidden="true" />
          </div>
          <div className="mt-3 flex items-end gap-2">
            <strong className="text-2xl font-semibold tabular-nums tracking-[-0.03em]">{value}</strong>
            <span className="pb-0.5 text-[11px] text-ink-muted">{note}</span>
          </div>
        </div>
      ))}
    </section>
  );
}
