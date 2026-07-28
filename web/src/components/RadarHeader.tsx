import { AlertTriangle, CalendarDays, Database, RefreshCcw } from "lucide-react";
import type { RadarRun } from "../types/radar";
import { formatFullDate, formatWindow, freshnessLabel, isStale } from "../utils/format";
import { GenerateRadarButton } from "./GenerateRadarButton";

interface RadarHeaderProps {
  run: RadarRun;
  onRefresh: () => void;
  refreshing: boolean;
  onGenerate: () => void;
  generating: boolean;
  generationElapsed: number;
  generationError?: string;
}

export function RadarHeader({
  run,
  onRefresh,
  refreshing,
  onGenerate,
  generating,
  generationElapsed,
  generationError,
}: RadarHeaderProps) {
  const stale = isStale(run.generated_at);
  return (
    <header className="space-y-5">
      <div className="flex flex-col justify-between gap-5 sm:flex-row sm:items-end">
        <div>
          <p className="text-xs font-semibold tracking-[0.16em] text-brand">MARKET INTELLIGENCE · A 股</p>
          <h1 className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-ink sm:text-[34px]">
            今日研究雷达
          </h1>
          <p className="mt-2 text-sm leading-6 text-ink-muted sm:text-[15px]">
            <span className="block sm:inline">{formatFullDate(run.window_end)}</span>
            <span className="hidden sm:inline"> · </span>
            <span className="block sm:inline">过去 24 小时的市场事件与研究线索</span>
          </p>
        </div>
        <div className="flex flex-col items-start gap-2 sm:items-end">
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={onRefresh}
              disabled={refreshing || generating}
              className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-line bg-surface px-4 text-sm font-semibold text-ink transition hover:border-brand/40 hover:text-brand disabled:cursor-wait disabled:opacity-60"
            >
              <RefreshCcw className={`size-4 ${refreshing ? "animate-spin" : ""}`} aria-hidden="true" />
              刷新快照
            </button>
            <GenerateRadarButton
              onGenerate={onGenerate}
              generating={generating}
              elapsedSeconds={generationElapsed}
              error={generationError}
            />
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-3 rounded-xl border border-line bg-surface px-4 py-3 text-xs text-ink-muted sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
          <span className="inline-flex items-center gap-2">
            <CalendarDays className="size-4 text-brand" aria-hidden="true" />
            {formatWindow(run.window_start, run.window_end)}
          </span>
          <span className="inline-flex items-center gap-2">
            <Database className="size-4 text-info" aria-hidden="true" />
            {freshnessLabel(run.generated_at)}
          </span>
        </div>
        <span
          className={`inline-flex w-fit items-center gap-1.5 rounded-full px-2.5 py-1 font-semibold ${
            stale ? "bg-warning-soft text-warning" : "bg-brand-soft text-brand"
          }`}
        >
          {stale && <AlertTriangle className="size-3.5" aria-hidden="true" />}
          {stale ? "数据已超过 24 小时" : "最新成功快照"}
        </span>
      </div>
    </header>
  );
}
