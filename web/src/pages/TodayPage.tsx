import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { AlertTriangle, ArrowUpRight, Newspaper } from "lucide-react";
import { CandidateQueue } from "../components/CandidateQueue";
import { EmptyState, ErrorState, LoadingState } from "../components/PageState";
import { EventCard } from "../components/EventCard";
import { GenerationProgress } from "../components/GenerationProgress";
import { ImpactRankings } from "../components/ImpactRankings";
import { RadarHeader } from "../components/RadarHeader";
import { RunAudit } from "../components/RunAudit";
import { ResearchCandidates } from "../components/ResearchCandidates";
import { SummaryStrip } from "../components/SummaryStrip";
import { ValidationTasks } from "../components/ValidationTasks";
import { WatchlistAlerts } from "../components/WatchlistAlerts";
import { loadLatestRadar } from "../data/loadLatestRadar";
import {
  cancelDailyRadar,
  generateDailyRadar,
  loadCurrentRadar,
} from "../data/generateDailyRadar";

export function TodayPage() {
  const [clock, setClock] = useState(() => Date.now());
  const query = useQuery({
    queryKey: ["daily-radar-latest"],
    queryFn: loadLatestRadar,
    retry: false,
    staleTime: Number.POSITIVE_INFINITY,
  });
  const currentQuery = useQuery({
    queryKey: ["daily-radar-current"],
    queryFn: loadCurrentRadar,
    retry: false,
    refetchInterval: (current) => {
      const status = current.state.data?.status;
      return status === "queued" || status === "running" ? 2000 : false;
    },
  });
  const current = currentQuery.data;
  const currentActive = current?.status === "queued" || current?.status === "running";
  const generation = useMutation({
    mutationFn: generateDailyRadar,
    onSuccess: () => currentQuery.refetch(),
  });
  const cancellation = useMutation({
    mutationFn: cancelDailyRadar,
    onSuccess: () => currentQuery.refetch(),
  });
  useEffect(() => {
    if (!currentActive) return;
    const timer = window.setInterval(() => {
      setClock(Date.now());
    }, 1000);
    return () => window.clearInterval(timer);
  }, [currentActive]);
  const refetchLatest = query.refetch;
  useEffect(() => {
    if (current?.status === "succeeded") void refetchLatest();
  }, [current?.status, refetchLatest]);
  const generationElapsed = currentActive
    ? Math.max(0, Math.floor(
      (clock - new Date(current?.started_at ?? clock).getTime()) / 1000,
    ))
    : 0;
  const generationProps = {
    onGenerate: () => {
      generation.mutate();
    },
    generating: generation.isPending || currentActive,
    generationElapsed,
    generationError: generation.error?.message || currentQuery.error?.message,
  };
  const progress = current ? (
    <GenerationProgress
      state={current}
      onCancel={() => cancellation.mutate()}
      onResume={() => generation.mutate()}
      cancelling={cancellation.isPending}
      resuming={generation.isPending}
    />
  ) : null;

  if (query.isPending) return <LoadingState />;
  if (query.isError) {
    return (
      <>
        <ErrorState message={query.error.message} onRetry={() => void query.refetch()} {...generationProps} />
        {progress}
      </>
    );
  }

  const radar = query.data;
  if (radar === null || radar.events.length === 0) {
    return (
      <>
        <EmptyState {...generationProps} />
        {progress}
      </>
    );
  }
  const attentionEvents = radar.events.filter(
    (event) => event.analysis_tier === "pro" || event.analysis_tier === "flash" || event.importance_level === "high",
  );

  return (
    <div className="mx-auto min-w-0 max-w-[1380px] overflow-x-hidden px-4 py-7 sm:px-7 lg:px-9 lg:py-10">
      <RadarHeader
        run={radar.run}
        onRefresh={() => void query.refetch()}
        refreshing={query.isFetching}
        {...generationProps}
      />
      {progress}

      {radar.run.warnings.length > 0 && (
        <div className="mt-5 flex min-w-0 items-start gap-3 overflow-hidden rounded-xl border border-warning/20 bg-warning-soft px-4 py-3 text-xs leading-5 text-warning">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <div className="min-w-0">
            <p className="font-semibold">数据说明</p>
            <details>
              <summary className="cursor-pointer list-none break-all">
                {radar.run.warnings[0]}{radar.run.warnings.length > 1 && `（另 ${radar.run.warnings.length - 1} 条）`}
              </summary>
              {radar.run.warnings.length > 1 && <ul className="mt-1 space-y-1">{radar.run.warnings.slice(1).map((warning) => <li key={warning}>· {warning}</li>)}</ul>}
            </details>
          </div>
        </div>
      )}

      <div className="mt-6"><SummaryStrip summary={radar.summary} /></div>
      <WatchlistAlerts alerts={radar.alerts} />
      <ImpactRankings events={radar.events} groups={radar.candidate_groups} />

      <div className="mt-7 grid min-w-0 items-start gap-6 xl:grid-cols-[minmax(0,1.65fr)_minmax(330px,0.75fr)]">
        <section className="min-w-0" aria-labelledby="events-heading">
          <div className="mb-4 flex items-end justify-between gap-4">
            <div>
              <p className="text-[11px] font-semibold tracking-[0.14em] text-brand">TOP EVENTS</p>
              <h2 id="events-heading" className="mt-1 text-xl font-semibold tracking-[-0.025em]">今日核心事件</h2>
            </div>
            <span className="hidden items-center gap-1 text-xs text-ink-muted sm:inline-flex">
              按独立来源与新鲜度排序<ArrowUpRight className="size-3.5" />
            </span>
            <a href="/events" className="text-xs font-semibold text-brand hover:underline">查看全部 {radar.summary.total_event_count} 个事件</a>
          </div>
          <div className="space-y-4">
            {attentionEvents.map((event) => <EventCard key={event.id} event={event} />)}
            {attentionEvents.length === 0 && (
              <div className="rounded-xl border border-line bg-surface p-8 text-center text-sm text-ink-muted">
                当前没有 Pro、Flash 或高重要度事件。<a href="/events" className="ml-1 font-semibold text-brand hover:underline">查看完整事件目录</a>
              </div>
            )}
          </div>
        </section>

        <aside className="min-w-0 space-y-4 xl:sticky xl:top-6" aria-label="研究队列">
          <div className="flex items-center gap-2">
            <Newspaper className="size-4 text-brand" aria-hidden="true" />
            <h2 className="text-sm font-semibold">候选研究队列</h2>
          </div>
          <ResearchCandidates candidates={radar.research_candidates} />
          <CandidateQueue groups={radar.candidate_groups} />
          <ValidationTasks tasks={radar.validation_tasks} />
          <RunAudit steps={radar.run.steps} />
        </aside>
      </div>

      <footer className="mt-8 flex flex-col justify-between gap-2 border-t border-line py-5 text-[11px] text-ink-muted sm:flex-row">
        <p>{radar.disclaimer}</p>
        <p>Finance Research Lab · Evidence before narrative</p>
      </footer>
    </div>
  );
}
