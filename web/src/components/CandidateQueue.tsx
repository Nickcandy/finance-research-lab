import { Ban, CheckCircle2, CircleDashed, Star } from "lucide-react";
import type { CandidateGroups, ScoredRadarCandidate, VerificationStatus } from "../types/radar";
import { CandidateRow } from "./CandidateRow";

interface CandidateQueueProps {
  groups: CandidateGroups;
}

interface GroupProps {
  title: string;
  description: string;
  candidates: ScoredRadarCandidate[];
  status: VerificationStatus;
}

const groupIcons = {
  verified: CheckCircle2,
  unverified: CircleDashed,
  excluded: Ban,
};

function CandidateGroup({ title, description, candidates, status }: GroupProps) {
  const Icon = groupIcons[status];
  return (
    <section className="rounded-xl border border-line bg-surface px-4">
      <div className="flex items-start gap-3 border-b border-line py-4">
        <div className={`grid size-8 place-items-center rounded-lg ${status === "verified" ? "bg-brand-soft text-brand" : status === "unverified" ? "bg-warning-soft text-warning" : "bg-surface-muted text-excluded"}`}>
          <Icon className="size-4" aria-hidden="true" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-sm font-semibold text-ink">{title}</h3>
            <span className="text-xs font-semibold tabular-nums text-ink-muted">{candidates.length}</span>
          </div>
          <p className="mt-1 text-[11px] leading-4 text-ink-muted">{description}</p>
        </div>
      </div>
      {candidates.length === 0 ? (
        <p className="py-5 text-xs text-ink-muted">暂无候选</p>
      ) : (
        candidates.map((candidate) => <CandidateRow key={candidate.symbol} candidate={candidate} compact={status === "excluded"} />)
      )}
    </section>
  );
}

export function CandidateQueue({ groups }: CandidateQueueProps) {
  return (
    <div className="space-y-3">
      {groups.watchlist.length > 0 && (
        <div className="flex items-center gap-2 rounded-xl border border-info/15 bg-info-soft px-4 py-3 text-xs text-info">
          <Star className="size-4 fill-white" aria-hidden="true" />
          Watchlist 命中 {groups.watchlist.length} 个候选
        </div>
      )}
      <CandidateGroup title="已校验候选" description="公司、财报与行情证据已形成闭环" candidates={groups.verified} status="verified" />
      <CandidateGroup title="待确认候选" description="保留研究线索，但尚不进入正式判断" candidates={groups.unverified} status="unverified" />
      <CandidateGroup title="风险排除" description="主营校验不符或仅有名称映射" candidates={groups.excluded} status="excluded" />
    </div>
  );
}
