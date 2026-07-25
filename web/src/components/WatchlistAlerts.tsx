import { ShieldAlert } from "lucide-react";
import type { RadarAlert } from "../types/radar";
import { ImpactBadge } from "./ImpactBadge";
import { HorizonBadges } from "./ImpactHorizon";

interface WatchlistAlertsProps {
  alerts: RadarAlert[];
}

export function WatchlistAlerts({ alerts }: WatchlistAlertsProps) {
  if (alerts.length === 0) return null;
  return (
    <section className="mt-6 rounded-xl border border-risk/20 bg-risk-soft p-4 sm:p-5" aria-labelledby="watchlist-alerts-heading">
      <div className="flex items-start gap-3">
        <div className="grid size-9 shrink-0 place-items-center rounded-lg bg-white/70 text-risk">
          <ShieldAlert className="size-4" aria-hidden="true" />
        </div>
        <div>
          <h2 id="watchlist-alerts-heading" className="text-sm font-semibold text-ink">Watchlist 风险预警</h2>
          <p className="mt-1 text-xs text-ink-muted">仅显示已验证且达到中高强度的负面或多空分化事件。</p>
        </div>
      </div>
      <div className="mt-4 grid gap-3 lg:grid-cols-2">
        {alerts.map((alert) => (
          <a key={alert.id} href={`/events/${alert.event_id}`} className="rounded-lg border border-risk/15 bg-white/70 p-4 transition hover:border-risk/30">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm font-semibold text-ink">{alert.name} <span className="font-normal text-ink-muted">{alert.symbol}</span></p>
              <span className="rounded-full bg-risk px-2 py-0.5 text-[10px] font-semibold text-white">{alert.severity === "high" ? "高风险" : "中风险"}</span>
            </div>
            <p className="mt-2 line-clamp-2 text-xs leading-5 text-ink-muted">{alert.event_title}</p>
            <div className="mt-3 flex flex-wrap gap-1.5">
              <ImpactBadge kind="direction" value={alert.direction} />
              <ImpactBadge kind="score" value={alert.impact_score} />
              <ImpactBadge kind="confidence" value={alert.confidence} />
              <HorizonBadges positive={null} negative={alert.negative_horizon} />
            </div>
            <p className="mt-3 text-xs leading-5 text-ink">{alert.reasoning || "暂无风险说明"}</p>
          </a>
        ))}
      </div>
    </section>
  );
}
