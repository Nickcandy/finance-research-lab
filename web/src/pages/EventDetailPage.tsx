import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ExternalLink, FileText, LoaderCircle } from "lucide-react";
import { CandidateRow } from "../components/CandidateRow";
import { EventCard } from "../components/EventCard";
import { ErrorState, LoadingState } from "../components/PageState";
import { loadEventAnalysis, startEventAnalysis } from "../data/eventAnalysis";
import { loadLatestRadar } from "../data/loadLatestRadar";
import { formatDateTime } from "../utils/format";

interface EventDetailPageProps {
  eventId: string;
}

export function EventDetailPage({ eventId }: EventDetailPageProps) {
  const client = useQueryClient();
  const radarQuery = useQuery({ queryKey: ["daily-radar-latest"], queryFn: loadLatestRadar });
  const summary = radarQuery.data?.all_events.find((event) => event.id === eventId);
  const analysisApplicable = summary?.analysis_status !== "not_applicable";
  const analysisQuery = useQuery({
    queryKey: ["event-analysis", eventId],
    queryFn: () => loadEventAnalysis(eventId),
    enabled: Boolean(summary) && analysisApplicable,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "running" ? 2_000 : false;
    },
  });
  const mutation = useMutation({
    mutationFn: () => startEventAnalysis(eventId),
    onSuccess: (data) => {
      client.setQueryData(["event-analysis", eventId], data);
      void client.invalidateQueries({ queryKey: ["daily-radar-latest"] });
    },
  });

  if (radarQuery.isPending) return <LoadingState />;
  if (radarQuery.isError) return <ErrorState message={radarQuery.error.message} onRetry={() => void radarQuery.refetch()} />;
  if (!summary) return <ErrorState message="当前日报中找不到这个聚类事件。" onRetry={() => { window.location.href = "/events"; }} />;

  const analysis = analysisQuery.data;
  const busy = mutation.isPending || analysis?.status === "queued" || analysis?.status === "running";
  return (
    <div className="mx-auto max-w-5xl px-4 py-7 sm:px-7 lg:py-10">
      <a href="/events" className="inline-flex items-center gap-1.5 text-sm font-semibold text-brand hover:underline"><ArrowLeft className="size-4" />全部事件</a>
      <div className="mt-5 rounded-xl border border-line bg-surface p-5 sm:p-7">
        <div className="flex flex-wrap items-center gap-2 text-xs text-ink-muted">
          <span>排名 {summary.rank}</span><span>·</span>
          <span>{formatDateTime(summary.latest_published_at)}</span><span>·</span>
          <span>{summary.report_count} 条报道</span>
        </div>
        <h1 className="mt-3 text-2xl font-semibold leading-9 tracking-[-0.03em]">{summary.title}</h1>
        <div className="mt-6 border-t border-line pt-5">
          <h2 className="text-sm font-semibold">聚类成员</h2>
          <div className="mt-3 space-y-3">
            {summary.items.map((item, index) => (
              <div key={`${item.url}-${index}`} className="rounded-lg bg-canvas px-4 py-3 text-sm">
                <p className="font-medium">{item.headline}</p>
                <p className="mt-1 text-xs text-ink-muted">{item.source} · {formatDateTime(item.published_at)}</p>
                {item.url && <a href={item.url} target="_blank" rel="noreferrer" className="mt-2 inline-flex items-center gap-1 text-xs text-info hover:underline">查看来源<ExternalLink className="size-3" /></a>}
              </div>
            ))}
          </div>
        </div>
      </div>

      <section className="mt-6" aria-labelledby="analysis-heading">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div><p className="text-[11px] font-semibold tracking-[0.14em] text-brand">EVENT ANALYSIS</p><h2 id="analysis-heading" className="mt-1 text-xl font-semibold">单事件分析报告</h2></div>
          {!analysisApplicable ? null : analysis?.status === "succeeded" ? (
            <a href={`/api/radars/latest/events/${eventId}/report`} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 rounded-lg bg-brand px-4 py-2.5 text-sm font-semibold text-white"><FileText className="size-4" />查看 Markdown</a>
          ) : (
            <button disabled={busy} onClick={() => mutation.mutate()} className="inline-flex items-center gap-2 rounded-lg bg-brand px-4 py-2.5 text-sm font-semibold text-white disabled:cursor-wait disabled:opacity-60">
              {busy && <LoaderCircle className="size-4 animate-spin" />}{busy ? "分析进行中" : analysis?.status === "failed" ? "重新分析" : "生成分析报告"}
            </button>
          )}
        </div>

        {!analysisApplicable && (
          <div className="mt-4 rounded-xl border border-dashed border-line bg-surface p-8 text-center">
            <p className="text-sm font-semibold text-ink">纯行情播报，不进入事件分析</p>
            <p className="mt-2 text-xs leading-5 text-ink-muted">该聚类只描述个股价格、涨跌幅或成交结果，没有可验证的事件原因。后续会由独立的涨跌原因归因流程处理。</p>
          </div>
        )}

        {(mutation.isError || analysisQuery.isError) && <p className="mt-4 rounded-lg bg-risk-soft p-3 text-sm text-risk">{mutation.error?.message || analysisQuery.error?.message}</p>}
        {analysis?.status === "failed" && <p className="mt-4 rounded-lg bg-risk-soft p-3 text-sm text-risk">{analysis.error || "事件分析失败，可以重新尝试。"}</p>}
        {busy && <div className="mt-4 rounded-xl border border-line bg-surface p-6 text-sm text-ink-muted">正在读取公司、财报与行情证据，页面会自动更新。</div>}
        {analysis?.status === "succeeded" && analysis.event && (
          <div className="mt-4 space-y-4">
            <EventCard event={analysis.event} />
            <section className="rounded-xl border border-line bg-surface px-4" aria-labelledby="candidate-impact-heading">
              <div className="border-b border-line py-4">
                <h3 id="candidate-impact-heading" className="text-sm font-semibold text-ink">候选股影响</h3>
                <p className="mt-1 text-xs text-ink-muted">影响指数衡量事件与公司的研究关联强度，指数不是股价预测。</p>
              </div>
              {analysis.event.candidates.length > 0
                ? analysis.event.candidates.map((candidate) => <CandidateRow key={candidate.symbol} candidate={candidate} />)
                : <p className="py-5 text-xs text-ink-muted">暂无候选股</p>}
            </section>
          </div>
        )}
        {analysisApplicable && !analysis && !analysisQuery.isPending && <div className="mt-4 rounded-xl border border-dashed border-line bg-surface p-8 text-center text-sm text-ink-muted">该事件尚未分析。生成后会保存到本次日报运行下。</div>}
      </section>
    </div>
  );
}
