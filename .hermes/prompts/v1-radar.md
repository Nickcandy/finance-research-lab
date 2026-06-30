# V1 投资机会雷达日报 — Codex 开发提示词

## 目标

在 `finance-research-lab` 项目里新增 `radar` 命令：输入多条新闻 URL + 股票池 CSV，输出一份每日机会雷达 Markdown 报告。

---

## 项目背景

这是一个 Python CLI 项目，分层清晰：

```
src/finance_research_lab/
  cli.py          # CLI argparse，当前只有 trace-news 子命令
  models.py       # 核心数据类：RawNews, ResearchReport, WatchlistItem …
  agent_models.py # ToolResult, AgentStep, AgentRun
  tools.py        # 工具封装：fetch_news_tool, read_watchlist_tool, trace_news_tool …
  workflow.py     # run_news_trace_workflow → 代码控制的 Agent v0 流程
  news_fetcher.py # URL → RawNews 的 HTML 抓取
  news_trace.py   # 主题识别、股票池映射、规则 fallback
  research_agent.py # LLM Structured Outputs Agent
  report.py       # Markdown 报告渲染
tests/
  test_workflow.py
data/
  watchlist.example.csv
reports/
```

**当前已完成 V0**：`finance-lab trace-news --url ... --watchlist ... --output ...` 跑通，27 个测试通过。

**关键约定**：
- workflow 由代码控制，LLM 只负责解释/分析/生成报告
- 用 `ToolResult` / `AgentStep` / `AgentRun` 记录每一步
- 测试用 monkeypatch mock 掉 fetch 和 agent 调用
- 代码规范：`ruff check src tests && pytest -q`

---

## V1 要做什么

新增 `radar` 子命令，用法：

```bash
finance-lab radar \
  --urls "https://.../news1" "https://.../news2" "https://.../news3" \
  --watchlist data/watchlist.example.csv \
  --output reports/2026-06-24-opportunity-radar.md
```

内部流程：对每一条 URL 复用好 V0 的 `fetch_news_tool → read_watchlist_tool → trace_news_tool → render_report_tool` 管线，汇总所有结果到一份雷达日报中。

---

## 输出报告格式

```markdown
# 今日投资机会雷达 2026-06-24

> 分析新闻数：3
> 用途：研究辅助，不构成投资建议。

## 1. 今日核心结论

（汇总所有新闻的关键发现，用 3-5 条 bullet point）

## 2. 热点事件追源

（每条新闻一个子章节）

### 2.1 新闻标题1

- 来源 / URL
- 事件类型、主题
- 产业链路径（谁付钱 → 谁收钱 → 链条）
- 涉及标的及影响

### 2.2 新闻标题2

（同上）

## 3. 中长线观察

（筛选 impact_type=direct, impact_strength=high/medium 的标的，列出核心逻辑和证据）

## 4. 短期交易机会

（筛选 stage=启动/验证 且有 action_state=可小仓试/等回调 的标的）

## 5. 高位不追 / 风险排除

（筛选 stage=高潮/分歧 或 impact_strength=low 或 action_state=高潮勿追 的标的）

## 6. 明天验证点

（汇总所有新闻的 validation_tasks，去重后列出）

## 7. 待复盘记录

（空列表，留待后续填充）
```

> 注意：如果某章节没有对应数据，写"暂无"而不是跳过。

---

## 具体改什么

### 1. 新建 `src/finance_research_lab/radar_report.py`

新增 `render_opportunity_radar(reports: list[ResearchReport], report_date=None) -> str` 函数，按上面的 Markdown 模板渲染。

- `reports` 是从每条 URL 得到的 `ResearchReport` 列表
- 复用 `models.py` 里的 `ResearchReport.stage`, `.action_state`, `.stock_impacts` 字段来做筛选
- 各个 section 的筛选逻辑：
  - **中长线观察**：`impact_type == "direct"` 且 `impact_strength in ("high", "medium")`
  - **短期交易机会**：`stage in ("启动", "验证")` 且 `action_state in ("可小仓试", "等回调")`
  - **高位不追**：`stage in ("高潮", "分歧")` 或 `impact_strength == "low"` 或 `action_state == "高潮勿追"`
  - **明天验证点**：汇总所有 `validation_tasks`，按 `question` 去重

### 2. 修改 `src/finance_research_lab/workflow.py`

新增 `run_radar_workflow(urls: list[str], watchlist_path, output_path) -> AgentRun` 函数：

```python
def run_radar_workflow(urls, watchlist_path, output_path) -> AgentRun:
    # Step 1: 读取股票池（一次）
    # Step 2-N: 对每条 url，走 fetch → trace 管线，收集 ResearchReport
    #   - fetch_news_tool(url) → ToolResult
    #   - trace_news_tool(fetch_result.output, watchlist) → ToolResult
    #   - 每条 URL 产出一个 ResearchReport，收集到列表
    # Step N+1: render_opportunity_radar(reports) → markdown
    # Step N+2: write_report_tool(markdown, output_path)
    # 返回 AgentRun("radar", steps, output_path)
```

注意：
- 股票池只读一次
- 某条 URL 抓取或分析失败，记录 error step 但**继续处理下一条**
- 最终 render 只渲染成功的那些 ResearchReport

### 3. 修改 `src/finance_research_lab/cli.py`

在 `build_parser()` 里新增 `radar` 子命令：

```python
radar_parser = subparsers.add_parser("radar", help="Generate daily opportunity radar report")
radar_parser.add_argument("--urls", nargs="+", required=True, help="One or more news URLs")
radar_parser.add_argument("--watchlist", default="data/watchlist.example.csv")
radar_parser.add_argument("--output", default="reports/opportunity-radar.md")
radar_parser.set_defaults(func=radar_cmd)
```

新增 `radar_cmd(args)` 函数，调用 `run_radar_workflow`，输出 step 状态和最终文件路径。

### 4. 新建测试文件 `tests/test_radar.py`

至少覆盖：
- `test_run_radar_workflow_multiple_urls`：2 条 URL 都成功，报告包含两条新闻的标题
- `test_run_radar_workflow_one_url_fails`：一条 URL 抓取失败，另一条成功，报告仍生成
- `test_run_radar_workflow_all_fail`：所有 URL 失败，不写文件，返回 error steps
- `test_radar_report_sections`：验证报告中长线观察/短期交易机会/高位不追 section 的筛选逻辑

复用 `test_workflow.py` 的 mock 模式：monkeypatch `fetch_news_tool` 和 `analyze_research_report_with_agent`。

---

## 重要提醒

1. **不要改 V0 的 trace-news** — 所有新代码独立添加
2. **复用不要复制** — workflow 里直接 import 现有的 `fetch_news_tool`、`read_watchlist_tool`、`trace_news_tool`、`write_report_tool`
3. **每个 ResearchReport 已有完整字段**（stage, action_state, stock_impacts 带 impact_type/impact_strength），筛选直接用
4. **跑通测试后**检查 `ruff check src tests` 是否通过

---

## 验收标准

```bash
PYTHONPATH=src python -m finance_research_lab.cli radar \
  --urls "https://example.com/news1" "https://example.com/news2" \
  --watchlist data/watchlist.example.csv \
  --output reports/demo-opportunity-radar.md

# 输出 reports/demo-opportunity-radar.md
# pytest -q 全部通过（新测试 + 旧 27 个）
# ruff check src tests 通过
```
