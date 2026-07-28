import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Search, Trash2 } from "lucide-react";
import { useState } from "react";
import { ErrorState, LoadingState } from "../components/PageState";
import { addWatchlistItem, loadWatchlist, removeWatchlistItem, searchStocks } from "../data/watchlist";

export function WatchlistPage() {
  const client = useQueryClient();
  const [keyword, setKeyword] = useState("");
  const watchlist = useQuery({ queryKey: ["watchlist"], queryFn: loadWatchlist });
  const search = useQuery({
    queryKey: ["stock-search", keyword],
    queryFn: () => searchStocks(keyword),
    enabled: keyword.trim().length > 0,
  });
  const add = useMutation({
    mutationFn: addWatchlistItem,
    onSuccess: async () => { setKeyword(""); await client.invalidateQueries({ queryKey: ["watchlist"] }); },
  });
  const remove = useMutation({
    mutationFn: removeWatchlistItem,
    onSuccess: () => client.invalidateQueries({ queryKey: ["watchlist"] }),
  });

  if (watchlist.isPending) return <LoadingState />;
  if (watchlist.isError) return <ErrorState message={watchlist.error.message} onRetry={() => void watchlist.refetch()} />;
  const existing = new Set(watchlist.data.map((item) => item.symbol));
  const mutationError = add.error?.message || remove.error?.message;

  return (
    <div className="mx-auto max-w-5xl px-4 py-7 sm:px-7 lg:py-10">
      <p className="text-[11px] font-semibold tracking-[0.14em] text-brand">WATCHLIST</p>
      <h1 className="mt-1 text-3xl font-semibold tracking-[-0.035em]">观察池管理</h1>
      <p className="mt-2 text-sm text-ink-muted">观察池只影响提醒和研究排序，不限制系统发现其他 A 股。</p>

      <section className="mt-6 rounded-xl border border-line bg-surface p-5">
        <label className="flex items-center gap-2 rounded-lg border border-line px-3 py-2.5">
          <Search className="size-4 text-ink-muted" aria-hidden="true" />
          <span className="sr-only">搜索股票</span>
          <input value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="输入股票代码或名称" className="min-w-0 flex-1 bg-transparent text-sm outline-none" />
        </label>
        {search.isFetching && <p className="mt-3 text-xs text-ink-muted">正在搜索…</p>}
        {search.isError && <p className="mt-3 text-xs text-risk">{search.error.message}</p>}
        {(search.data ?? []).length > 0 && (
          <div className="mt-3 divide-y divide-line rounded-lg border border-line">
            {search.data!.map((stock) => (
              <div key={stock.symbol} className="flex items-center justify-between gap-4 px-4 py-3">
                <div><p className="text-sm font-semibold">{stock.name} <span className="text-xs text-ink-muted">{stock.symbol}</span></p><p className="mt-1 text-xs text-ink-muted">{stock.industry || "行业待补充"}</p></div>
                <button type="button" disabled={existing.has(stock.symbol) || add.isPending} onClick={() => add.mutate(stock.symbol)} className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-brand px-3 text-xs font-semibold text-white disabled:opacity-50"><Plus className="size-3.5" />{existing.has(stock.symbol) ? "已加入" : "加入"}</button>
              </div>
            ))}
          </div>
        )}
        {mutationError && <p className="mt-3 text-xs text-risk">{mutationError}</p>}
      </section>

      <section className="mt-6 space-y-3" aria-label="当前观察池">
        {watchlist.data.map((item) => (
          <article key={item.symbol} className="flex items-start justify-between gap-4 rounded-xl border border-line bg-surface p-4">
            <div className="min-w-0"><h2 className="font-semibold">{item.name} <span className="text-xs font-normal text-ink-muted">{item.symbol}</span></h2><p className="mt-1 text-xs text-ink-muted">{item.industry || item.market} · {item.themes.join(" / ") || "暂无主题"}</p>{item.thesis && <p className="mt-2 text-xs leading-5 text-ink-muted">{item.thesis}</p>}</div>
            <button type="button" disabled={remove.isPending} onClick={() => { if (window.confirm(`确认删除 ${item.name}（${item.symbol}）？`)) remove.mutate(item.symbol); }} className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-lg border border-risk/20 px-3 text-xs font-semibold text-risk disabled:opacity-50"><Trash2 className="size-3.5" />删除</button>
          </article>
        ))}
      </section>
    </div>
  );
}
