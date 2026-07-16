import { Check, ClipboardCheck } from "lucide-react";
import type { ValidationTask } from "../types/radar";

interface ValidationTasksProps {
  tasks: ValidationTask[];
}

export function ValidationTasks({ tasks }: ValidationTasksProps) {
  return (
    <section className="rounded-xl border border-line bg-surface p-4 sm:p-5">
      <div className="flex items-center gap-3">
        <div className="grid size-9 place-items-center rounded-lg bg-brand-soft text-brand">
          <ClipboardCheck className="size-4.5" aria-hidden="true" />
        </div>
        <div>
          <h3 className="text-sm font-semibold">明日验证任务</h3>
          <p className="mt-0.5 text-[11px] text-ink-muted">把尚未回答的问题留在研究链路里</p>
        </div>
      </div>
      <ol className="mt-4 space-y-3">
        {tasks.map((task, index) => (
          <li key={`${task.question}-${index}`} className="flex gap-3 rounded-lg bg-canvas p-3">
            <span className="grid size-5 shrink-0 place-items-center rounded border border-line bg-surface text-[10px] text-ink-muted">
              {task.status === "done" ? <Check className="size-3" /> : index + 1}
            </span>
            <div>
              <p className="text-xs font-medium leading-5 text-ink">{task.question}</p>
              <p className="mt-1 text-[11px] leading-4 text-ink-muted">需要：{task.data_needed}</p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
