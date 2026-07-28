import { AlertTriangle, BarChart3, ShieldAlert } from "lucide-react";
import type { CandidateGroups, RadarEvent, ScoredRadarCandidate } from "../types/radar";
import { ImpactCandidate } from "./ImpactCandidate";

interface ImpactRankingsProps {
  events: RadarEvent[];
  groups: CandidateGroups;
}

const tierLabels = {
  pro: "Pro 深度分析",
  flash: "Flash 简报",
  deterministic: "规则摘要",
  not_applicable: "不适用",
};

export function ImpactRankings({ events, groups }: ImpactRankingsProps) {
  const candidates = uniqueCandidates([...groups.verified, ...groups.unverified])
    .filter((candidate) => candidate.score_status !== "insufficient_evidence" && Number.isFinite(candidate.positive_magnitude))
    .sort((left, right) => maxImpact(right) - maxImpact(left));
  const verifyFirst = candidates.filter((candidate) => candidate.priority_level === "verify_first");
  const watchlistRisks = candidates.filter(
    (candidate) => candidate.watchlist_hit && candidate.negative_magnitude >= 60,
  );
  const rankedEvents = [...events].sort(
    (left, right) => right.event_importance - left.event_importance,
  );

  return (
    <section className="mt-7 rounded-xl border border-line bg-surface p-4 sm:p-6" aria-labelledby="impact-rankings-heading">
      <div className="flex items-start gap-3">
        <div className="grid size-9 place-items-center rounded-lg bg-brand-soft text-brand">
          <BarChart3 className="size-4" aria-hidden="true" />
        </div>
        <div>
          <h2 id="impact-rankings-heading" className="text-lg font-semibold text-ink">影响优先级</h2>
          <p className="mt-1 text-xs text-ink-muted">影响分是研究优先级，不是收益预测，也不代表投资建议。</p>
        </div>
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        <RankingPanel title="重大事件榜">
          {rankedEvents.slice(0, 5).map((event) => (
            <div key={event.id} className="border-b border-line py-3 last:border-0">
              <div className="flex items-start justify-between gap-3">
                <a href={`/events/${event.id}`} className="text-sm font-semibold text-ink hover:text-brand">{event.title}</a>
                <span className="font-semibold tabular-nums text-brand">{event.event_importance}</span>
              </div>
              <p className="mt-1 text-[11px] text-ink-muted">{tierLabels[event.analysis_tier]} · {event.importance_level}</p>
            </div>
          ))}
        </RankingPanel>

        <RankingPanel title="重点股票榜">
          {candidates.slice(0, 8).map((candidate) => (
            <ImpactCandidate key={candidate.symbol} candidate={candidate} />
          ))}
        </RankingPanel>

        <RankingPanel title="高影响待核验" warning>
          {verifyFirst.length === 0
            ? <EmptyText />
            : verifyFirst.map((candidate) => (
              <p key={candidate.symbol} className="border-b border-line py-3 text-sm last:border-0">
                <span className="font-semibold">{candidate.name}</span>
                <span className="ml-2 text-warning">置信度 {candidate.confidence}，优先补充原始证据</span>
              </p>
            ))}
        </RankingPanel>

        <RankingPanel title="Watchlist 评分风险" risk>
          {watchlistRisks.length === 0
            ? <EmptyText />
            : watchlistRisks.map((candidate) => (
              <p key={candidate.symbol} className="border-b border-line py-3 text-sm last:border-0">
                <span className="font-semibold">{candidate.name}</span>
                <span className="ml-2 text-risk">负向影响 {candidate.negative_magnitude}</span>
              </p>
            ))}
        </RankingPanel>
      </div>
    </section>
  );
}

function RankingPanel({ title, children, warning, risk }: { title: string; children: React.ReactNode; warning?: boolean; risk?: boolean }) {
  const Icon = risk ? ShieldAlert : warning ? AlertTriangle : BarChart3;
  return (
    <section className="rounded-lg border border-line bg-canvas px-4">
      <h3 className="flex items-center gap-2 border-b border-line py-3 text-sm font-semibold">
        <Icon className={`size-4 ${risk ? "text-risk" : warning ? "text-warning" : "text-brand"}`} />{title}
      </h3>
      {children}
    </section>
  );
}

function uniqueCandidates(values: ScoredRadarCandidate[]) {
  return [...new Map(values.map((candidate) => [candidate.symbol, candidate])).values()];
}

function maxImpact(candidate: ScoredRadarCandidate) {
  return Math.max(candidate.positive_magnitude, candidate.negative_magnitude);
}

function EmptyText() {
  return <p className="py-4 text-xs text-ink-muted">暂无</p>;
}
