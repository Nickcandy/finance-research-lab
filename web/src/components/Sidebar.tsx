import { Activity, BookOpenText, CircleDot, Clock3, FlaskConical, ListTree, Star } from "lucide-react";

export function Sidebar() {
  const path = window.location.pathname;
  return (
    <aside className="hidden min-h-screen w-60 shrink-0 flex-col bg-sidebar px-5 py-7 text-white lg:flex">
      <div className="flex items-center gap-3 px-1">
        <div className="grid size-10 place-items-center rounded-xl bg-brand text-sm font-bold">F</div>
        <div>
          <p className="text-[15px] font-semibold tracking-tight">Finance Lab</p>
          <p className="mt-0.5 text-xs text-sidebar-muted">A 股研究工作台</p>
        </div>
      </div>

      <nav className="mt-10" aria-label="主导航">
        <p className="px-3 text-[11px] font-medium tracking-[0.16em] text-sidebar-muted">研究</p>
        <a
          href="/today"
          aria-current={path === "/today" || path === "/" ? "page" : undefined}
          className={`mt-3 flex items-center gap-3 rounded-xl px-3 py-3 text-sm font-semibold ${path === "/today" || path === "/" ? "bg-brand" : "text-sidebar-muted"}`}
        >
          <CircleDot className="size-4" aria-hidden="true" />
          今日雷达
        </a>
        <a
          href="/events"
          aria-current={path.startsWith("/events") ? "page" : undefined}
          className={`mt-1 flex items-center gap-3 rounded-xl px-3 py-3 text-sm font-semibold ${path.startsWith("/events") ? "bg-brand" : "text-sidebar-muted"}`}
        >
          <ListTree className="size-4" aria-hidden="true" />
          全部事件
        </a>
        <a
          href="/watchlist"
          aria-current={path === "/watchlist" ? "page" : undefined}
          className={`mt-1 flex items-center gap-3 rounded-xl px-3 py-3 text-sm font-semibold ${path === "/watchlist" ? "bg-brand" : "text-sidebar-muted"}`}
        >
          <Star className="size-4" aria-hidden="true" />
          观察池
        </a>
        <span className="mt-1 flex cursor-not-allowed items-center gap-3 rounded-xl px-3 py-3 text-sm text-sidebar-muted">
          <Clock3 className="size-4" aria-hidden="true" />
          运行记录
          <span className="ml-auto text-[10px]">稍后</span>
        </span>
      </nav>

      <div className="mt-auto space-y-3">
        <div className="rounded-xl border border-white/10 bg-white/5 p-4">
          <div className="flex items-center gap-2 text-xs text-sidebar-muted">
            <Activity className="size-3.5" aria-hidden="true" />
            数据状态
          </div>
          <div className="mt-3 flex items-center gap-2 text-sm font-medium">
            <span className="size-2 rounded-full bg-[#9CC6B8]" />
            最新成功快照
          </div>
          <p className="mt-2 text-xs leading-5 text-sidebar-muted">同花顺 · AkShare · BaoStock</p>
        </div>
        <div className="flex items-center gap-2 px-2 text-[11px] text-sidebar-muted">
          <BookOpenText className="size-3.5" aria-hidden="true" />
          证据优先
          <span className="text-white/20">·</span>
          <FlaskConical className="size-3.5" aria-hidden="true" />
          本地运行
        </div>
      </div>
    </aside>
  );
}
