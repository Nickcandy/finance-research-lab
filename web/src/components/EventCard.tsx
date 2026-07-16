import {
  AlertTriangle,
  ArrowRight,
  ChevronDown,
  ExternalLink,
  FileText,
  Link2,
  Users,
} from "lucide-react";
import type { RadarEvent } from "../types/radar";
import { formatDateTime } from "../utils/format";
import { StatusBadge } from "./StatusBadge";

interface EventCardProps {
  event: RadarEvent;
}

export function EventCard({ event }: EventCardProps) {
  const verified = event.candidates.filter((candidate) => candidate.verification_status === "verified").length;
  const pending = event.candidates.filter((candidate) => candidate.verification_status === "unverified").length;
  return (
    <article className="min-w-0 overflow-hidden rounded-xl border border-line bg-surface transition hover:border-brand/30 hover:shadow-panel">
      <div className="p-5 sm:p-6">
        <div className="flex gap-4">
          <div className="grid size-9 shrink-0 place-items-center rounded-full bg-brand-soft text-sm font-bold tabular-nums text-brand">
            {String(event.rank).padStart(2, "0")}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2 text-[11px] font-medium text-ink-muted">
              <span>{formatDateTime(event.latest_published_at)}</span>
              <span className="text-line">/</span>
              <span>{event.source_count} 个独立来源</span>
              <span className="text-line">/</span>
              <span>{event.report_count} 条报道</span>
            </div>
            <h2 className="mt-2 break-all text-[18px] font-semibold leading-7 tracking-[-0.02em] text-ink sm:text-xl">
              {event.title}
            </h2>
          </div>
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-2">
          <span className="rounded-full border border-brand/15 bg-brand-soft px-2.5 py-1 text-[11px] font-semibold text-brand">
            {event.event_type}
          </span>
          {event.themes.slice(0, 3).map((theme) => (
            <span key={theme} className="rounded-full border border-line px-2.5 py-1 text-[11px] text-ink-muted">
              {theme}
            </span>
          ))}
          {event.analysis_status === "failed" && (
            <span className="rounded-full bg-risk-soft px-2.5 py-1 text-[11px] font-semibold text-risk">分析失败</span>
          )}
        </div>

        {event.value_chain.chain_steps.length > 0 && (
          <div className="mt-5 rounded-lg bg-canvas px-4 py-3">
            <p className="text-[10px] font-semibold tracking-[0.14em] text-ink-muted">VALUE CHAIN</p>
            <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs font-medium text-ink">
              {event.value_chain.chain_steps.map((step, index) => (
                <span key={`${step}-${index}`} className="contents">
                  <span>{step}</span>
                  {index < event.value_chain.chain_steps.length - 1 && (
                    <ArrowRight className="size-3.5 text-brand/60" aria-hidden="true" />
                  )}
                </span>
              ))}
            </div>
          </div>
        )}

        {event.warnings.length > 0 && (
          <div className="mt-4 flex gap-2 rounded-lg border border-warning/15 bg-warning-soft/70 px-3 py-2.5 text-xs leading-5 text-warning">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            <span>{event.warnings[0]}</span>
          </div>
        )}

        <div className="mt-5 flex flex-wrap items-center gap-3 border-t border-line pt-4 text-xs text-ink-muted">
          <span className="inline-flex items-center gap-1.5"><Users className="size-3.5" />{event.candidates.length} 个候选</span>
          {verified > 0 && <StatusBadge status="verified" />}
          {pending > 0 && <StatusBadge status="unverified" />}
        </div>
      </div>

      <details className="group border-t border-line bg-[#FCFBF8]">
        <summary className="flex cursor-pointer list-none items-center justify-between px-5 py-3.5 text-xs font-semibold text-ink transition hover:text-brand sm:px-6">
          <span className="inline-flex items-center gap-2"><FileText className="size-4 text-brand" />查看事实、来源与风险</span>
          <ChevronDown className="size-4 transition group-open:rotate-180" aria-hidden="true" />
        </summary>
        <div className="grid gap-5 border-t border-line px-5 py-5 text-xs leading-5 sm:grid-cols-2 sm:px-6">
          <div>
            <p className="font-semibold text-ink">关键事实</p>
            <ul className="mt-2 space-y-1.5 text-ink-muted">
              {event.key_facts.map((fact) => <li key={fact}>· {fact}</li>)}
            </ul>
          </div>
          <div>
            <p className="font-semibold text-ink">来源链接</p>
            <div className="mt-2 space-y-2">
              {event.source_urls.length === 0 && <p className="text-ink-muted">暂无可用 URL</p>}
              {event.source_urls.map((url, index) => (
                <a key={url} href={url} target="_blank" rel="noreferrer" className="flex items-center gap-2 text-info hover:underline">
                  <Link2 className="size-3.5" />来源 {index + 1}<ExternalLink className="size-3" />
                </a>
              ))}
            </div>
          </div>
        </div>
      </details>
    </article>
  );
}
