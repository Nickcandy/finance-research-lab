import { CircleStop, LoaderCircle, RotateCcw } from "lucide-react";
import type { RadarGenerationStage, RadarGenerationState } from "../types/radar";

interface GenerationProgressProps {
  state: RadarGenerationState;
  onCancel: () => void;
  onResume: () => void;
  cancelling: boolean;
  resuming: boolean;
}

const stageLabels: Record<RadarGenerationStage, string> = {
  fetch_news: "拉取新闻",
  cluster: "聚类事件",
  extract_claims: "提取事实",
  score_events: "计算影响",
  analyze_events: "分析事件",
  finalize: "生成快照",
};

export function GenerationProgress({
  state,
  onCancel,
  onResume,
  cancelling,
  resuming,
}: GenerationProgressProps) {
  const active = state.status === "queued" || state.status === "running";
  const completed = state.news.filter((item) =>
    item.analysis_status === "succeeded" || item.analysis_status === "fallback"
  ).length;
  return (
    <section className="mt-5 rounded-xl border border-brand/20 bg-brand-soft/40 p-4" aria-label="日报更新进度">
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold text-ink">
            {active && <LoaderCircle className="size-4 animate-spin text-brand" aria-hidden="true" />}
            {stageLabels[state.stage]} · {state.progress.completed}/{state.progress.total || "待确认"}
          </div>
          <p className="mt-1 text-xs text-ink-muted">
            已完成 {completed}/{state.news.length} 条新闻 · 最后更新 {new Date(state.updated_at).toLocaleTimeString("zh-CN")}
          </p>
          {state.error && <p className="mt-2 text-xs text-risk">{state.error}</p>}
        </div>
        {active ? (
          <button
            type="button"
            onClick={onCancel}
            disabled={cancelling}
            className="inline-flex h-9 items-center justify-center gap-2 rounded-lg border border-risk/30 bg-surface px-3 text-xs font-semibold text-risk disabled:opacity-60"
          >
            <CircleStop className="size-4" aria-hidden="true" />
            {cancelling ? "正在停止" : "停止更新"}
          </button>
        ) : state.resumable ? (
          <button
            type="button"
            onClick={onResume}
            disabled={resuming}
            className="inline-flex h-9 items-center justify-center gap-2 rounded-lg bg-brand px-3 text-xs font-semibold text-white disabled:opacity-60"
          >
            <RotateCcw className="size-4" aria-hidden="true" />
            {resuming ? "正在继续" : "继续更新"}
          </button>
        ) : null}
      </div>

      {state.news.length > 0 && (
        <div className="mt-4 max-h-64 space-y-2 overflow-y-auto border-t border-brand/10 pt-3">
          {state.news.slice(0, 50).map((item) => (
            <div key={item.item_id} className="flex items-start justify-between gap-3 rounded-lg bg-surface/80 px-3 py-2 text-xs">
              <div className="min-w-0">
                {item.url ? (
                  <a className="line-clamp-2 font-medium text-ink hover:text-brand" href={item.url} target="_blank" rel="noreferrer">
                    {item.headline}
                  </a>
                ) : <p className="line-clamp-2 font-medium text-ink">{item.headline}</p>}
                <p className="mt-1 text-[11px] text-ink-muted">{item.source} · {new Date(item.published_at).toLocaleTimeString("zh-CN")}</p>
              </div>
              <span className="shrink-0 rounded-full bg-canvas px-2 py-1 text-[10px] font-semibold text-ink-muted">
                {statusLabel(item.analysis_status)}
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function statusLabel(status: RadarGenerationState["news"][number]["analysis_status"]) {
  if (status === "succeeded") return "已分析";
  if (status === "fallback") return "规则降级";
  if (status === "running") return "分析中";
  return "待分析";
}
