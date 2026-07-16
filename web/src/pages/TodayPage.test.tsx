import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import fixture from "../fixtures/daily-radar.json";

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
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the complete research radar from the latest API snapshot", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(apiResponse(fixture)));
    const user = userEvent.setup();
    renderPage();

    expect(screen.getByLabelText("正在加载今日雷达")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "今日研究雷达" })).toBeInTheDocument();
    expect(screen.getByText("京东推出京麦 AI 经营中心，面向商家开放智能经营能力")).toBeInTheDocument();
    expect(screen.getByText("宁德时代")).toBeInTheDocument();
    expect(screen.getByText("Watchlist 命中 2 个候选")).toBeInTheDocument();
    expect(screen.getByText("研究辅助，不构成投资建议。")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "已校验候选" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "待确认候选" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "风险排除" })).toBeInTheDocument();
    expect(screen.getByText("京麦 AI 是否向第三方 SaaS 开放接口或产生明确采购？")).toBeInTheDocument();
    expect(screen.getByText(/当前展示前端预览 fixture/)).toBeInTheDocument();

    const verifiedGroup = screen.getByRole("heading", { name: "已校验候选" }).closest("section");
    expect(verifiedGroup).not.toBeNull();
    await user.click(within(verifiedGroup!).getByText("宁德时代"));
    expect(within(verifiedGroup!).getByText(/贸易政策变化/)).toBeInTheDocument();

    await user.click(screen.getAllByText("查看事实、来源与风险")[0]!);
    expect(screen.getAllByRole("link", { name: /来源 1/ })[0]).toHaveAttribute("href", expect.stringContaining("example.com"));
  });

  it("keeps the loading state visible while the API request is pending", () => {
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => undefined)));
    renderPage();

    expect(screen.getByLabelText("正在加载今日雷达")).toBeInTheDocument();
  });

  it("renders an actionable empty state when the API returns 404", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(apiResponse({ error: "radar_not_found" }, 404)));
    renderPage();

    expect(await screen.findByRole("heading", { name: "还没有可展示的日报" })).toBeInTheDocument();
    expect(screen.getByText(/finance-lab daily-radar/)).toBeInTheDocument();
  });

  it("renders an API error and retries the latest snapshot", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        apiResponse({ error: "invalid_radar_snapshot", message: "日报快照格式无效" }, 500),
      )
      .mockResolvedValueOnce(apiResponse(fixture));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByRole("heading", { name: "日报暂时无法加载" })).toBeInTheDocument();
    expect(screen.getByText("日报快照格式无效")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "重新读取" }));
    expect(await screen.findByRole("heading", { name: "今日研究雷达" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("marks snapshots older than 24 hours as stale", async () => {
    const staleFixture = {
      ...fixture,
      run: { ...fixture.run, generated_at: "2020-01-01T00:00:00+08:00" },
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(apiResponse(staleFixture)));
    renderPage();

    expect(await screen.findByText("数据已超过 24 小时")).toBeInTheDocument();
  });
});

function apiResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
