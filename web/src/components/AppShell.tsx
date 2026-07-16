import type { ReactNode } from "react";
import { Sidebar } from "./Sidebar";

interface AppShellProps {
  children: ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  return (
    <div className="min-h-screen bg-canvas text-ink lg:flex">
      <Sidebar />
      <div className="border-b border-white/10 bg-sidebar px-4 py-3 text-white lg:hidden">
        <div className="mx-auto flex max-w-6xl items-center gap-3">
          <div className="grid size-9 place-items-center rounded-lg bg-brand text-sm font-bold">F</div>
          <div>
            <p className="text-sm font-semibold">Finance Lab</p>
            <p className="text-[11px] text-sidebar-muted">今日雷达 · 前端预览</p>
          </div>
        </div>
      </div>
      <main className="min-w-0 flex-1">{children}</main>
    </div>
  );
}
