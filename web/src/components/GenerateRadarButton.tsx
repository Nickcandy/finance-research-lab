import { LoaderCircle, Play } from "lucide-react";

interface GenerateRadarButtonProps {
  onGenerate: () => void;
  generating: boolean;
  elapsedSeconds: number;
  error?: string;
}

export function GenerateRadarButton({
  onGenerate,
  generating,
  elapsedSeconds,
  error,
}: GenerateRadarButtonProps) {
  return (
    <div className="flex flex-col items-start gap-2">
      <button
        type="button"
        onClick={onGenerate}
        disabled={generating}
        className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-brand px-4 text-sm font-semibold text-white transition hover:bg-brand/90 disabled:cursor-wait disabled:opacity-60"
      >
        {generating ? <LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> : <Play className="size-4" aria-hidden="true" />}
        {generating ? `生成中 · 已运行 ${formatElapsed(elapsedSeconds)}` : "重新生成日报"}
      </button>
      {error && <p className="text-xs text-risk">{error}</p>}
    </div>
  );
}

function formatElapsed(seconds: number): string {
  const minutes = Math.floor(seconds / 60).toString().padStart(2, "0");
  const remaining = (seconds % 60).toString().padStart(2, "0");
  return `${minutes}:${remaining}`;
}
