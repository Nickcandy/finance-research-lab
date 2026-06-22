# finance-research-lab 当前实现说明

生成日期：2026-06-22

## 现在已经完成什么

当前项目已经完成第一版 MVP 的本地闭环：抓取静态 HTML 新闻、读取股票池、分析新闻事件并生成一份 Markdown 研究报告。项目定位仍然是个人研究辅助和作品集展示，不输出确定性买卖建议，也没有自动交易逻辑。

在此基础上，项目已经补了一层 Agent-ready 数据契约和 Agent v0 结构：`trace_news_tool` 会优先尝试用兼容 Chat Completions 的 Structured Outputs 填充 `ResearchReport`，失败时回退到本地规则 fallback，并通过 tools + workflow 记录每一步 `AgentStep`。

已完成的核心能力：

- 提供 `finance-lab trace-news` 命令行入口。
- 从 URL 提取新闻标题、站点、发布时间和正文，抓取不完整时终止分析。
- 从 CSV 文件读取关注股票池。
- 支持兼容 Chat Completions 的 Structured Outputs 生成严格 `ResearchReport`。
- LLM key 缺失、请求失败、模型拒答、JSON 解析失败或 schema 校验失败时，自动回退到本地规则。
- 规则 fallback 基于新闻标题和正文关键词识别主题，例如 AI、数据中心、光模块、稳定币、支付、券商、CXO、商业航天。
- 规则 fallback 基于关键词对新闻类型做简单分类，并按主题重合度映射股票池标的。
- 生成 Agent-ready `ResearchReport`，包含原始事件、事件理解、产业链路径、股票影响映射、阶段状态和验证任务。
- 输出 Markdown 研究报告，包含事件理解、产业链拆解、股票影响、证据、风险和验证点。
- 已有最小单元测试覆盖主题识别、股票池映射、报告核心章节和 Agent v0 workflow 执行步骤。

## 当前代码结构

```text
src/finance_research_lab/
  cli.py          # CLI 参数解析和 trace-news 命令执行
  models.py       # WatchlistItem、NewsTrace、ResearchReport 等核心数据结构
  agent_models.py # ToolResult、AgentStep、AgentRun
  tools.py        # fetch_news / read_watchlist / trace_news / render_report / write_report 工具封装
  workflow.py     # 代码控制的 Agent v0 workflow
  news_fetcher.py # 静态 HTML 新闻抓取和正文提取
  news_trace.py   # 股票池读取、主题识别、新闻分类、追源构建
  research_agent.py          # LLM Structured Outputs Agent 封装
  research_report_schema.py  # ResearchReport JSON Schema 和 parser
  report.py       # Markdown 报告渲染
tests/
  test_news_trace.py
  test_report.py
  test_workflow.py
prompts/
  investment_research_agent.md
data/
  watchlist.example.csv
reports/
  .gitkeep
```

## 主流程

1. 用户执行 `finance-lab trace-news`，传入新闻 URL、股票池路径和输出路径。
2. `fetch_news_tool()` 获取静态 HTML 并生成可信 `RawNews`。
3. `read_watchlist_tool()` 读取 CSV 股票池。
4. `trace_news_tool()` 优先调用 LLM Agent，让模型按 JSON Schema 返回 `ResearchReport`。
5. 如果 Agent 不可用或输出不合格，`build_research_report()` 使用本地规则 fallback 生成 `ResearchReport`。
6. parser 校验结构和股票代码，代码使用抓取结果覆盖模型返回的 `raw_news`。
7. 报告渲染为 Markdown 并写入输出文件。

## 数据模型

`WatchlistItem` 表示关注标的：

- `symbol`：代码。
- `name`：名称。
- `market`：市场。
- `themes`：主题标签。
- `thesis`：关注逻辑。
- `risks`：风险点。

`ResearchReport` 是后续 Agent 要填充的核心结构：

- `RawNews`：原始标题、来源、URL、发布时间和正文。
- `EventAnalysis`：事件类型、主题、关键事实、来源质量、置信度和推理说明。
- `ValueChainTrace`：付款方、收款方、产业链路径、影响方向和推理说明。
- `StockImpact`：单个标的的影响类型、强度、证据、风险和理由。
- `ValidationTask`：后续要验证的问题、所需数据和状态。
- `stage`、`action_state`：当前阶段和动作状态。

`NewsTrace` 仍保留为兼容旧测试和旧调用的轻量结构，但 CLI 当前已经通过 `ResearchReport` 生成报告。

## 规则逻辑

OpenAI Agent 可用时，事件理解、产业链路径和股票影响映射由模型生成，但必须符合 `ResearchReport` JSON Schema，且 `stock_impacts` 只能引用传入 watchlist 中的 symbol。

规则 fallback 仍完全基于内置关键词表 `THEME_KEYWORDS`。例如标题中出现 `AI`、`data center`、`capex`、`光模块` 等词，会匹配到 AI、数据中心、光模块等主题。

股票池映射规则目前用于生成 `StockImpact`：

- 主题交集大于等于 2 个：`direct / high`。
- 主题交集等于 1 个：`indirect / medium`。
- 如果主题词出现在标的 thesis 中：`sentiment / low`。

产业链路径目前只对两个方向有专门模板：

- AI / 数据中心 / 光模块。
- 稳定币 / 支付。

其他主题会落到通用占位路径，需要人工补充判断。

## 命令示例

安装后运行：

```bash
finance-lab trace-news \
  --url "https://example.com/news/article" \
  --watchlist data/watchlist.example.csv \
  --output reports/demo-news-trace.md
```

不安装脚本时运行：

```bash
PYTHONPATH=src python -m finance_research_lab.cli trace-news \
  --url "https://example.com/news/article" \
  --watchlist data/watchlist.example.csv \
  --output reports/demo-news-trace.md
```

## 已有测试

当前测试覆盖：

- `infer_themes()` 能从 AI capex 标题中识别 AI 和数据中心主题。
- `build_trace()` 能把 AI 数据中心光模块相关标的映射为直接受益。
- `build_research_report()` 能生成事件理解、产业链路径、股票影响和验证任务。
- `parse_research_report()` 能校验 Agent 返回的 strict JSON。
- OpenAI Agent fake response 成功时能生成 `ResearchReport`，refusal、坏 JSON、HTTP error 和缺 key 时能 fallback。
- `render_research_report()` 输出事件理解、股票影响映射和验证清单。
- workflow 能通过新版 `ResearchReport` 写出 Markdown 报告。

运行方式：

```bash
python3 -m pytest -q
```

## 还没有做什么

当前版本还没有实现以下能力：

- 不支持付费墙、登录页面或 JavaScript 动态渲染新闻。
- 没有新闻来源时间线和传播链去重。
- 没有行情、财务、估值或成交额数据接入。
- 没有数据库、后端服务或 Web 前端。
- 没有回测、策略信号或自动交易。
- 没有 RAG、行情、财务、公告等外部数据源适配。

## CodeGraph 状态

本次已在仓库根目录执行 `codegraph init`。初始化结果：

- 索引文件数：7。
- 节点数：41。
- 边数：66。

`.codegraph/` 是本地索引数据库目录，已加入根 `.gitignore`，不参与版本控制。
