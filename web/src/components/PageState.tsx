import { AlertCircle, FileSearch, RefreshCcw, TerminalSquare } from "lucide-react";
import { GenerateRadarButton } from "./GenerateRadarButton";

export function LoadingState() {
  return (
    <div className="mx-auto max-w-[1380px] animate-pulse px-4 py-8 sm:px-7 lg:px-9 lg:py-10" aria-label="正在加载今日雷达">
      <div className="h-3 w-48 rounded bg-line" />
      <div className="mt-4 h-10 w-64 rounded bg-line" />
      <div className="mt-3 h-4 w-96 max-w-full rounded bg-line/70" />
      <div className="mt-8 grid grid-cols-2 overflow-hidden rounded-xl border border-line bg-surface lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <div key={index} className="h-28 border-r border-line p-5 last:border-r-0">
            <div className="h-3 w-16 rounded bg-line" />
            <div className="mt-5 h-7 w-12 rounded bg-line" />
          </div>
        ))}
      </div>
      <div className="mt-7 grid gap-5 xl:grid-cols-[minmax(0,1.65fr)_minmax(320px,0.75fr)]">
        <div className="space-y-4">
          {Array.from({ length: 3 }).map((_, index) => <div key={index} className="h-52 rounded-xl border border-line bg-surface" />)}
        </div>
        <div className="h-[520px] rounded-xl border border-line bg-surface" />
      </div>
    </div>
  );
}

interface ErrorStateProps {
  message: string;
  onRetry: () => void;
  onGenerate?: () => void;
  generating?: boolean;
  generationElapsed?: number;
  generationError?: string;
}

export function ErrorState({ message, onRetry, onGenerate, generating = false, generationElapsed = 0, generationError }: ErrorStateProps) {
  return (
    <div className="mx-auto flex min-h-[78vh] max-w-xl items-center px-5 py-12">
      <section className="w-full rounded-2xl border border-risk/20 bg-surface p-7 text-center shadow-panel sm:p-10">
        <div className="mx-auto grid size-12 place-items-center rounded-full bg-risk-soft text-risk"><AlertCircle className="size-5" /></div>
        <h1 className="mt-5 text-xl font-semibold">日报暂时无法加载</h1>
        <p className="mt-2 text-sm leading-6 text-ink-muted">{message}</p>
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          <button type="button" onClick={onRetry} disabled={generating} className="inline-flex h-10 items-center gap-2 rounded-lg border border-line bg-surface px-4 text-sm font-semibold text-ink hover:text-brand disabled:opacity-60">
            <RefreshCcw className="size-4" />重新读取
          </button>
          {onGenerate && <GenerateRadarButton onGenerate={onGenerate} generating={generating} elapsedSeconds={generationElapsed} error={generationError} />}
        </div>
      </section>
    </div>
  );
}

interface EmptyStateProps {
  onGenerate?: () => void;
  generating?: boolean;
  generationElapsed?: number;
  generationError?: string;
}

export function EmptyState({ onGenerate, generating = false, generationElapsed = 0, generationError }: EmptyStateProps) {
  return (
    <div className="mx-auto flex min-h-[78vh] max-w-2xl items-center px-5 py-12">
      <section className="w-full rounded-2xl border border-line bg-surface p-7 text-center shadow-panel sm:p-10">
        <div className="mx-auto grid size-12 place-items-center rounded-full bg-brand-soft text-brand"><FileSearch className="size-5" /></div>
        <h1 className="mt-5 text-xl font-semibold">还没有可展示的日报</h1>
        <p className="mt-2 text-sm leading-6 text-ink-muted">先在终端生成最近 24 小时的研究结果，然后刷新这个页面。</p>
        <div className="mt-6 flex items-start gap-3 rounded-xl bg-sidebar p-4 text-left text-xs leading-5 text-sidebar-muted">
          <TerminalSquare className="mt-0.5 size-4 shrink-0 text-white" />
          <code className="break-all">.venv/bin/finance-lab daily-radar --output reports/daily-radar.md</code>
        </div>
        {onGenerate && (
          <div className="mt-6 flex justify-center">
            <GenerateRadarButton onGenerate={onGenerate} generating={generating} elapsedSeconds={generationElapsed} error={generationError} />
          </div>
        )}
      </section>
    </div>
  );
}
