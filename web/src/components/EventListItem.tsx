import { ArrowRight, CheckCircle2, CircleDashed, Clock3, XCircle } from "lucide-react";
import type { RadarEventSummary } from "../types/radar";
import { formatDateTime } from "../utils/format";
import { StockActions } from "./StockActions";

interface EventListItemProps {
  event: RadarEventSummary;
  core: boolean;
}

const statusText = {
  succeeded: "已分析",
  failed: "分析失败",
  not_started: "未分析",
  queued: "排队中",
  running: "分析中",
  not_applicable: "纯行情播报，不进入事件分析",
} as const;

export function EventListItem({ event, core }: EventListItemProps) {
  const relatedStocks = event.related_stocks ?? [];
  const StatusIcon = event.analysis_status === "succeeded"
    ? CheckCircle2
    : event.analysis_status === "failed"
      ? XCircle
      : event.analysis_status === "running" || event.analysis_status === "queued"
        ? Clock3
        : CircleDashed;
  return (
    <article className="rounded-xl border border-line bg-surface p-4 transition hover:border-brand/30 sm:p-5">
      <div className="flex gap-4">
        <div className="grid size-9 shrink-0 place-items-center rounded-full bg-brand-soft text-xs font-bold tabular-nums text-brand">
          {String(event.rank).padStart(2, "0")}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2 text-[11px] text-ink-muted">
            <span>{formatDateTime(event.latest_published_at)}</span>
            <span>·</span><span>{event.report_count} 条报道</span>
            <span>·</span><span>{event.source_count} 个来源</span>
            {core && <span className="rounded-full bg-brand-soft px-2 py-0.5 font-semibold text-brand">核心事件</span>}
          </div>
          <h2 className="mt-2 break-all text-base font-semibold leading-6 text-ink">{event.title}</h2>
          {relatedStocks.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {relatedStocks.map((stock) => (
                <div key={stock.symbol} title={stock.reasoning} className="inline-flex flex-wrap items-center gap-2 rounded-lg border border-brand/20 bg-brand-soft px-2.5 py-1 text-[11px] font-semibold text-brand">
                  {stock.name} · {stock.symbol}
                  <StockActions symbol={stock.symbol} watchlistHit={stock.watchlist_hit ?? false} newsLinks={stock.news_links} compact />
                </div>
              ))}
            </div>
          )}
          <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
            <span className="inline-flex items-center gap-1.5 text-xs text-ink-muted">
              <StatusIcon className="size-3.5" />{statusText[event.analysis_status]}
            </span>
            <a href={`/events/${event.id}`} className="inline-flex items-center gap-1 text-xs font-semibold text-brand hover:underline">
              {event.analysis_status === "not_started" ? "生成分析" : "查看详情"}<ArrowRight className="size-3.5" />
            </a>
          </div>
        </div>
      </div>
    </article>
  );
}
