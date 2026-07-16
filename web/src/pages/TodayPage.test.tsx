import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import App from "../App";

function renderPage(path = "/today") {
  window.history.replaceState({}, "", path);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  );
}

describe("TodayPage", () => {
  it("renders the complete research radar from the preview snapshot", async () => {
    const user = userEvent.setup();
    renderPage();

    expect(screen.getByLabelText("正在加载今日雷达")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "今日研究雷达" })).toBeInTheDocument();
    expect(screen.getByText("京东推出京麦 AI 经营中心，面向商家开放智能经营能力")).toBeInTheDocument();
    expect(screen.getByText("宁德时代")).toBeInTheDocument();
    expect(screen.getByText("Watchlist 命中 2 个候选")).toBeInTheDocument();
    expect(screen.getByText("研究辅助，不构成投资建议。")).toBeInTheDocument();

    await user.click(screen.getAllByText("查看事实、来源与风险")[0]!);
    expect(screen.getAllByRole("link", { name: /来源 1/ })[0]).toHaveAttribute("href", expect.stringContaining("example.com"));
  });

  it("keeps the loading state visible for visual verification", () => {
    renderPage("/today?state=loading");

    expect(screen.getByLabelText("正在加载今日雷达")).toBeInTheDocument();
  });

  it("renders an actionable empty state", async () => {
    renderPage("/today?state=empty");

    expect(await screen.findByRole("heading", { name: "还没有可展示的日报" })).toBeInTheDocument();
    expect(screen.getByText(/finance-lab daily-radar/)).toBeInTheDocument();
  });

  it("renders the error and retry action", async () => {
    renderPage("/today?state=error");

    expect(await screen.findByRole("heading", { name: "日报暂时无法加载" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重新读取" })).toBeInTheDocument();
  });
});
