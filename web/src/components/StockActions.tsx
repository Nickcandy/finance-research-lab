import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, ExternalLink, Plus } from "lucide-react";
import { addWatchlistItem } from "../data/watchlist";
import type { NewsLink } from "../types/radar";

interface StockActionsProps {
  symbol: string;
  watchlistHit: boolean;
  newsLinks?: NewsLink[];
  compact?: boolean;
}

export function StockActions({ symbol, watchlistHit, newsLinks = [], compact = false }: StockActionsProps) {
  const client = useQueryClient();
  const mutation = useMutation({
    mutationFn: () => addWatchlistItem(symbol),
    onSuccess: () => client.invalidateQueries({ queryKey: ["watchlist"] }),
  });
  const added = watchlistHit || mutation.isSuccess;
  const visibleLinks = compact ? newsLinks.slice(0, 1) : newsLinks.slice(0, 3);

  return (
    <div className={`flex flex-wrap items-center gap-2 ${compact ? "" : "mt-3"}`}>
      {visibleLinks.map((link, index) => (
        <a
          key={link.url}
          href={link.url}
          target="_blank"
          rel="noreferrer"
          title={`${link.source} · ${link.headline}`}
          className="inline-flex items-center gap-1 text-[11px] font-semibold text-info hover:underline"
        >
          {compact ? `新闻 ${index + 1}` : link.headline}<ExternalLink className="size-3" />
        </a>
      ))}
      <button
        type="button"
        disabled={added || mutation.isPending}
        onClick={() => mutation.mutate()}
        aria-label={added ? "已在待选池" : mutation.isPending ? "加入中" : "加入待选池"}
        className="inline-flex items-center gap-1 rounded-md border border-brand/20 px-2 py-1 text-[11px] font-semibold text-brand disabled:cursor-default disabled:border-line disabled:text-ink-muted"
      >
        {added ? <Check className="size-3" /> : <Plus className="size-3" />}
        {compact ? (added ? "已加入" : "待选") : (added ? "已在待选池" : mutation.isPending ? "加入中" : "加入待选池")}
      </button>
      {mutation.isError && <span className="text-[11px] text-risk">{mutation.error.message}</span>}
    </div>
  );
}
