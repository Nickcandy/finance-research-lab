import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useMemo, useState } from "react";
import { EventListItem } from "../components/EventListItem";
import { EmptyState, ErrorState, LoadingState } from "../components/PageState";
import { loadLatestRadar } from "../data/loadLatestRadar";

const PAGE_SIZE = 50;

export function AllEventsPage() {
  const [keyword, setKeyword] = useState("");
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const query = useQuery({ queryKey: ["daily-radar-latest"], queryFn: loadLatestRadar });
  const filtered = useMemo(() => {
    const term = keyword.trim().toLocaleLowerCase();
    if (!term) return query.data?.all_events ?? [];
    return (query.data?.all_events ?? []).filter((event) =>
      [event.title, ...event.items.map((item) => item.headline), ...event.sources.map((source) => source.name), ...(event.related_stocks ?? []).flatMap((stock) => [stock.symbol, stock.name])]
        .some((value) => value.toLocaleLowerCase().includes(term)),
    );
  }, [keyword, query.data]);

  if (query.isPending) return <LoadingState />;
  if (query.isError) return <ErrorState message={query.error.message} onRetry={() => void query.refetch()} />;
  if (query.data === null) return <EmptyState />;

  const coreIds = new Set(query.data.events.map((event) => event.id));
  const visible = filtered.slice(0, visibleCount);
  return (
    <div className="mx-auto max-w-5xl px-4 py-7 sm:px-7 lg:py-10">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-[11px] font-semibold tracking-[0.14em] text-brand">EVENT CATALOG</p>
          <h1 className="mt-1 text-3xl font-semibold tracking-[-0.035em]">全部聚类事件</h1>
          <p className="mt-2 text-sm text-ink-muted">共 {query.data.summary.total_event_count} 个事件，按独立来源与新鲜度排序。</p>
        </div>
        <a href="/today" className="text-sm font-semibold text-brand hover:underline">返回今日雷达</a>
      </div>

      <label className="mt-6 flex items-center gap-2 rounded-xl border border-line bg-surface px-4 py-3">
        <Search className="size-4 text-ink-muted" aria-hidden="true" />
        <span className="sr-only">搜索事件</span>
        <input
          value={keyword}
          onChange={(event) => { setKeyword(event.target.value); setVisibleCount(PAGE_SIZE); }}
          placeholder="搜索事件标题、成员新闻或来源"
          className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-ink-muted"
        />
      </label>

      <div className="mt-5 space-y-3">
        {visible.map((event) => <EventListItem key={event.id} event={event} core={coreIds.has(event.id)} />)}
        {visible.length === 0 && <p className="rounded-xl border border-line bg-surface p-8 text-center text-sm text-ink-muted">没有匹配的事件</p>}
      </div>
      {visibleCount < filtered.length && (
        <button onClick={() => setVisibleCount((count) => count + PAGE_SIZE)} className="mt-5 w-full rounded-xl border border-line bg-surface py-3 text-sm font-semibold text-brand hover:border-brand/30">
          加载更多（还有 {filtered.length - visibleCount} 条）
        </button>
      )}
    </div>
  );
}
