import { FlaskConical } from "lucide-react";
import type { RadarResearchCandidate } from "../types/radar";
import { CandidateRow } from "./CandidateRow";

interface ResearchCandidatesProps {
  candidates: RadarResearchCandidate[];
}

export function ResearchCandidates({ candidates }: ResearchCandidatesProps) {
  return (
    <section className="rounded-xl border border-line bg-surface px-4" aria-labelledby="research-candidates-heading">
      <div className="flex items-start gap-3 border-b border-line py-4">
        <div className="grid size-8 place-items-center rounded-lg bg-brand-soft text-brand">
          <FlaskConical className="size-4" aria-hidden="true" />
        </div>
        <div>
          <h3 id="research-candidates-heading" className="text-sm font-semibold text-ink">今日研究候选</h3>
          <p className="mt-1 text-[11px] leading-4 text-ink-muted">已验证的正向中高强度线索，最多 10 个，不是买入建议。</p>
        </div>
      </div>
      {candidates.length > 0
        ? candidates.map((candidate) => <CandidateRow key={candidate.symbol} candidate={candidate} />)
        : <p className="py-5 text-xs text-ink-muted">今日暂无符合门槛的研究候选</p>}
    </section>
  );
}
