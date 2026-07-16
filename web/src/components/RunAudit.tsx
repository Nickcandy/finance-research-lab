import { CircleCheck, ListTree } from "lucide-react";
import type { RadarStep } from "../types/radar";

interface RunAuditProps {
  steps: RadarStep[];
}

export function RunAudit({ steps }: RunAuditProps) {
  return (
    <details className="group rounded-xl border border-line bg-surface">
      <summary className="flex cursor-pointer list-none items-center justify-between p-4 text-xs font-semibold">
        <span className="inline-flex items-center gap-2"><ListTree className="size-4 text-info" />运行审计</span>
        <span className="text-[11px] font-normal text-ink-muted">{steps.length} 个记录步骤</span>
      </summary>
      <div className="border-t border-line px-4 py-2">
        {steps.map((step) => (
          <div key={step.step_name} className="flex gap-3 border-b border-line py-3 last:border-b-0">
            <CircleCheck className={`mt-0.5 size-3.5 shrink-0 ${step.status === "success" ? "text-brand" : "text-risk"}`} />
            <div className="min-w-0">
              <p className="truncate text-[11px] font-semibold text-ink">{step.step_name}</p>
              <p className="mt-1 truncate text-[10px] text-ink-muted">{step.summary}</p>
            </div>
          </div>
        ))}
      </div>
    </details>
  );
}
