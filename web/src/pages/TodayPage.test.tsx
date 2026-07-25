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
    expect(screen.getAllByText("京东推出京麦 AI 经营中心，面向商家开放智能经营能力").length).toBeGreaterThan(0);
    expect(screen.getAllByText("宁德时代").length).toBeGreaterThan(0);
    expect(screen.getByText("Watchlist 命中 2 个候选")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Watchlist 风险预警" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "影响优先级" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "高影响待核验" })).toBeInTheDocument();
    expect(screen.getAllByText("正向 84").length).toBeGreaterThan(0);
    expect(screen.getAllByText("负向 18").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Pro 深度分析/).length).toBeGreaterThan(0);
    expect(screen.getByText(/影响分是研究优先级，不是收益预测/)).toBeInTheDocument();
    expect(screen.getByText("平安银行")).toBeInTheDocument();
    expect(screen.getByText("000001.SZ")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "今日研究候选" })).toBeInTheDocument();
    expect(screen.getByText(/不是买入建议/)).toBeInTheDocument();
    expect(screen.getByText("研究辅助，不构成投资建议。")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "已校验候选" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "待确认候选" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "风险排除" })).toBeInTheDocument();
    expect(screen.getByText("京麦 AI 是否向第三方 SaaS 开放接口或产生明确采购？")).toBeInTheDocument();
    expect(screen.getByText(/当前展示前端预览 fixture/)).toBeInTheDocument();

    const firstEvent = screen
      .getAllByText("京东推出京麦 AI 经营中心，面向商家开放智能经营能力")
      .map((element) => element.closest("article"))
      .find((element) => element !== null);
    expect(firstEvent).not.toBeNull();
    expect(within(firstEvent!).getByText("总体方向：利好")).toBeInTheDocument();
    expect(within(firstEvent!).getByText("事件重要度：86")).toBeInTheDocument();
    expect(within(firstEvent!).getByText("证据置信度：82")).toBeInTheDocument();

    const verifiedGroup = screen.getByRole("heading", { name: "已校验候选" }).closest("section");
    expect(verifiedGroup).not.toBeNull();
    expect(within(verifiedGroup!).getByText("直接影响 / 高强度")).toBeInTheDocument();
    expect(within(verifiedGroup!).getByText("方向：利好")).toBeInTheDocument();
    expect(within(verifiedGroup!).getByText("正向 84")).toBeInTheDocument();
    expect(within(verifiedGroup!).getByText("负向 18")).toBeInTheDocument();
    expect(within(verifiedGroup!).getByText("置信度：88")).toBeInTheDocument();
    expect(within(verifiedGroup!).getByText("正向周期：长期")).toBeInTheDocument();
    await user.click(within(verifiedGroup!).getByText("宁德时代"));
    expect(within(verifiedGroup!).getByText(/贸易政策变化/)).toBeInTheDocument();
    expect(within(verifiedGroup!).getByText("市场反应：短期（6～20个交易日）")).toBeInTheDocument();
    expect(within(verifiedGroup!).getByText(/市场层依据：/)).toBeInTheDocument();
    expect(within(verifiedGroup!).getByText("基本面兑现：长期（6～24个月）")).toBeInTheDocument();
    expect(within(verifiedGroup!).getByText(/基本面层失效条件：/)).toBeInTheDocument();
    expect(within(verifiedGroup!).getByText(/原文明确周期：2026-2028/)).toBeInTheDocument();
    expect(screen.getAllByText("负向周期：中期").length).toBeGreaterThan(0);

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

  it("rejects a v2.1 snapshot with a clear version error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(apiResponse({
      ...fixture,
      schema_version: "2.1",
    })));
    renderPage();

    expect(await screen.findByText(/仅支持 DailyRadarSnapshot 2.3/)).toBeInTheDocument();
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

  it("links to the full catalog when no attention event qualifies", async () => {
    const quietFixture = {
      ...fixture,
      events: fixture.events.map((event) => ({
        ...event,
        analysis_tier: "deterministic" as const,
        importance_level: "low" as const,
      })),
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(apiResponse(quietFixture)));
    renderPage();

    expect(await screen.findByText(/当前没有 Pro、Flash 或高重要度事件/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "查看完整事件目录" })).toHaveAttribute("href", "/events");
  });

  it("renders an explicit unknown value-chain state", async () => {
    const unknownChainFixture = {
      ...fixture,
      events: fixture.events.map((event, index) => index === 0 ? {
        ...event,
        value_chain: {
          ...event.value_chain,
          chain_steps: [],
          reasoning: "没有可审计的图谱关系",
        },
      } : event),
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(apiResponse(unknownChainFixture)));
    renderPage();

    expect(await screen.findByText("未识别到可验证价值链")).toBeInTheDocument();
    expect(screen.getByText("没有可审计的图谱关系")).toBeInTheDocument();
  });
});

describe("event catalog pages", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows all clustered events and filters them", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(apiResponse(fixture)));
    const user = userEvent.setup();
    renderPage("/events");

    expect(await screen.findByRole("heading", { name: "全部聚类事件" })).toBeInTheDocument();
    expect(screen.getByText("京东推出京麦 AI 经营中心，面向商家开放智能经营能力")).toBeInTheDocument();
    await user.type(screen.getByPlaceholderText("搜索事件标题、成员新闻或来源"), "动力电池");
    expect(screen.getByText("动力电池出口保持增长，海外产能与客户结构受关注")).toBeInTheDocument();
    expect(screen.queryByText("京东推出京麦 AI 经营中心，面向商家开放智能经营能力")).not.toBeInTheDocument();
  });

  it("loads the event catalog in batches of fifty", async () => {
    const events = Array.from({ length: 51 }, (_, index) => ({
      ...fixture.all_events[0]!,
      id: `evt_batch_${index}`,
      rank: index + 1,
      title: `批量事件 ${index + 1}`,
      items: [{ ...fixture.all_events[0]!.items[0]!, headline: `批量事件 ${index + 1}` }],
    }));
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(apiResponse({
      ...fixture,
      summary: { ...fixture.summary, total_event_count: 51 },
      all_events: events,
    })));
    const user = userEvent.setup();
    renderPage("/events");

    expect(await screen.findByText("批量事件 50")).toBeInTheDocument();
    expect(screen.queryByText("批量事件 51")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /加载更多/ }));
    expect(screen.getByText("批量事件 51")).toBeInTheDocument();
  });

  it("starts one event analysis from its detail page", async () => {
    const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/radars/latest") return Promise.resolve(apiResponse(fixture));
      if (init?.method === "POST") {
        return Promise.resolve(apiResponse({ run_id: fixture.run.id, event_id: fixture.all_events[0]!.id, status: "queued" }, 202));
      }
      return Promise.resolve(apiResponse({ error: "analysis_not_found" }, 404));
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderPage(`/events/${fixture.all_events[0]!.id}`);

    expect(await screen.findByRole("heading", { name: "单事件分析报告" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "候选股影响" })).not.toBeInTheDocument();
    expect(screen.queryByText(/指数不是股价预测/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "生成分析报告" }));
    expect(await screen.findByText("正在读取公司、财报与行情证据，页面会自动更新。")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/radars/latest/events/${fixture.all_events[0]!.id}/analysis`,
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("renders a completed event analysis and Markdown link", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation((input: RequestInfo | URL) => {
      if (String(input) === "/api/radars/latest") return Promise.resolve(apiResponse(fixture));
      return Promise.resolve(apiResponse({
        schema_version: "1.0",
        run_id: fixture.run.id,
        event_id: fixture.all_events[0]!.id,
        status: "succeeded",
        event: fixture.events[0],
        markdown: "# report",
      }));
    }));
    renderPage(`/events/${fixture.all_events[0]!.id}`);

    const link = await screen.findByRole("link", { name: "查看 Markdown" });
    expect(link).toHaveAttribute("href", `/api/radars/latest/events/${fixture.all_events[0]!.id}/report`);
    expect(screen.getByRole("heading", { name: "候选股影响" })).toBeInTheDocument();
    expect(screen.getByText(/指数不是股价预测/)).toBeInTheDocument();
    const candidate = screen.getByText("光云科技").closest("details");
    expect(candidate).not.toBeNull();
    expect(within(candidate!).getByText("间接影响 / 中强度")).toBeInTheDocument();
    expect(within(candidate!).getByText("方向：利好")).toBeInTheDocument();
    expect(within(candidate!).getByText("指数：+45")).toBeInTheDocument();
    expect(within(candidate!).getByText("置信度：中")).toBeInTheDocument();
  });

  it("disables analysis for pure stock price updates", async () => {
    const pureEvent = {
      ...fixture.all_events[0]!,
      id: "evt_pure_price_01",
      title: "中际旭创盘中涨超10%",
      analysis_status: "not_applicable" as const,
      exclusion_reason: "pure_stock_price_update" as const,
    };
    const pureFixture = {
      ...fixture,
      summary: { ...fixture.summary, total_event_count: 1, core_event_count: 0 },
      events: [],
      all_events: [pureEvent],
    };
    const fetchMock = vi.fn().mockResolvedValue(apiResponse(pureFixture));
    vi.stubGlobal("fetch", fetchMock);
    renderPage(`/events/${pureEvent.id}`);

    expect(await screen.findByText("纯行情播报，不进入事件分析")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /分析/ })).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

function apiResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
