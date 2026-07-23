# finance-research-lab

一个面向个人投资研究和 AI Agent 作品集展示的 Event-driven A 股研究工具。目标产品主动发现新闻、公告和行情异动，把多个来源聚合成市场事件，再拆解产业链和供给卡点、发现 A 股候选，并通过 tools 校验证据，最终生成可复盘的 Markdown 研究报告。

当前代码已实现 URL 手动研究入口和下游证据流程。URL 后续继续作为事件的 `source_url` 和单事件深挖入口，但不再是产品主输入。

## 目标

`finance-research-lab` 解决六个问题：

1. **事件发现**：主动拉取近期新闻、公告和行情异动，识别值得研究的热点。
2. **事件聚合**：把描述同一事件的多个来源去重、聚类，并保留全部来源。
3. **产业链拆解**：分析谁付钱、谁收钱、影响路径，以及难扩产、难替代的供给卡点。
4. **A股候选发现**：从事件和产业链卡点出发发现可能受影响的 A 股，不把 watchlist 当作候选边界。
5. **工具校验与报告输出**：通过 tools 校验公司、代码、主营和证据，生成 Markdown 研究报告。
6. **Agent 工程展示**：用 workflow、tools、structured output、fallback 和 agent steps 展示一个可解释的 AI Agent 雏形。

核心原则：

- 只输出研究辅助和观察框架，不直接给确定性买卖结论。
- 每条判断保留来源、规则和验证点。
- LLM 负责提出假设和解释，tools 负责校验事实，workflow 负责记录过程。
- `watchlist` 只是个人上下文、排序和复盘线索，不限制系统输出股票范围。
- 先做小而完整的本地工具，后续再扩展 A 股数据源、行情指标和回测。

## 目标 MVP

```text
新闻源 / 公司公告 / 行情异动
→ NewsItem 标准化
→ MarketEvent 去重与聚合
→ 热点事件排序
→ 产业链层级与供给卡点
→ A股候选发现
→ 公告 / 财报 / 行情证据核验
→ reports/daily-radar.md
```

## 当前已实现路径

主动事件发现主入口：

```text
同花顺最近 24 小时新闻
→ NewsItem
→ MarketEvent 聚类
→ Top 5 热点排序
→ LLM / 规则事件分析与 A 股候选发现
→ AkShare 公司证据 + BaoStock / AkShare 行情校验
→ reports/daily-radar.md
```

URL 手动深挖辅助入口：

```text
输入：
- data/watchlist.example.csv：个人关注股票上下文
- 一条或多条可直接访问的静态 HTML 新闻 URL

处理：
- 抓取新闻标题、来源、发布时间和正文
- 读取 watchlist 作为个人上下文
- 生成新闻追源卡片
- 根据 LLM 或规则做事件理解、产业链拆解和股票影响映射
- 输出 Markdown 报告

输出：
- reports/*.md
```

当前实现已经包含无 URL 的 `daily-radar` 主入口，以及 `trace-news`、`radar` 和 `research-agent`
三个 URL 手动研究入口。V2.1 已串通同花顺最近 24 小时新闻、事件聚类、Top 5 排序、逐事件产业链
分析、A 股候选发现和证据校验，并输出固定 Markdown 日报；更多事件源和完整 Serenity 分析仍在后续阶段。

V2.1 会把只描述个股涨跌、涨跌停、成交额或市值且没有原因的新闻标记为“纯行情播报”：它仍保留在
`/events`，但不进入核心 Top 5，也不能生成事件分析。已分析事件和股票会展示利好、利空、多空分化、
中性或待判断方向，以及由强度和影响类型透明计算的影响指数。`/today` 还会展示 Watchlist 风险预警和
全市场“今日研究候选”Top 10；这些结果用于安排研究优先级，不是收益预测或买入建议。

## 项目结构

```text
finance-research-lab/
  data/                         # 示例 watchlist / 后续本地数据缓存
  reports/                      # 生成的 Markdown 报告和 JSON 快照
  web/                          # React 今日雷达前端
  src/finance_research_lab/
    cli.py                      # 命令行入口
    models.py                   # 核心数据结构和 Agent-ready ResearchReport schema
    agent_models.py             # Agent run / step / tool result 数据结构
    tools.py                    # Agent 可调用工具封装
    workflow.py                 # 代码控制的 Agent v0 工作流
    event_sources.py            # 主动事件源
    event_clustering.py         # 确定性事件聚类与热点排序
    company_profiles.py         # 免费公司资料同步与本地缓存
    value_chains.py             # 确定性产业链节点和上下游映射
    daily_radar_report.py       # Event-driven 日报生成
    news_fetcher.py             # 静态 HTML 新闻抓取和正文提取
    news_trace.py               # 热点新闻追源逻辑
    report.py                   # Markdown 报告生成
  prompts/                      # Agent prompt 和输出约束
  tests/                        # 单元测试
```

## 快速开始

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[akshare,baostock,dev]'
pytest
```

本地 LLM key 放在 `.env`，不要提交真实 key：

```env
LLM_API_KEY=your_api_key_here
LLM_MODEL=gpt-4o-mini
LLM_BASE_URL=https://api.openai.com/v1
LLM_RESPONSE_FORMAT=json_schema
LLM_TIMEOUT_SECONDS=60
LLM_USAGE_STORE=data/agent_runs.sqlite3
```

`trace-news` 会优先尝试用兼容 OpenAI Chat Completions 的 Structured Outputs 生成严格的 `ResearchReport`。如果没有配置 key、LLM 请求失败、模型拒答、返回 JSON 解析失败或 schema 校验失败，会自动回退到本地规则 fallback，仍然生成 Markdown 报告。

`LLM_BASE_URL` 可以填写任意兼容 OpenAI Chat Completions 的服务地址；代码会请求 `{LLM_BASE_URL}/chat/completions`。不配置时默认使用 OpenAI 官方地址。

`LLM_RESPONSE_FORMAT` 控制结构化输出请求格式：

- `json_schema`：默认值，用于支持 OpenAI JSON Schema Structured Outputs 的服务。
- `json_object`：用于 DeepSeek 这类支持 JSON Output 但不支持 OpenAI `json_schema` 请求格式的服务。

所有 CLI 与网页按需分析发出的真实 LLM 请求都会写入 `LLM_USAGE_STORE`。CLI 和生成的
Markdown 报告会显示本次运行与上海自然日累计的 token 和已计价费用。当前阶段只记录、不阻止请求；
无法识别单价的模型仍可运行，但会标记为“费用不完整”。账本不保存 Prompt、模型输出或 API Key。

DeepSeek 示例：

```env
LLM_API_KEY=your_deepseek_key_here
LLM_MODEL=deepseek-v4-pro
LLM_BASE_URL=https://api.deepseek.com
LLM_RESPONSE_FORMAT=json_object
LLM_TIMEOUT_SECONDS=90
```

Structured Outputs 只能约束返回结构，不能保证投资结论正确；报告仍然只用于研究辅助，需要人工复核证据和风险。

## 命令示例

分批填充本地 A 股公司语义库。默认处理 100 只，重复执行直到输出 `pending=0`：

```bash
finance-lab sync-company-profiles \
  --universe data/a_share_universe.csv \
  --cache data/company_profile_cache \
  --output data/a_share_universe.csv
```

也可以运行全量续跑脚本。它每批处理 100 只，任一批失败时立即停止，否则持续到 `pending=0`：

```bash
./scripts/sync-company-profiles-all.sh
```

也可以只同步指定股票：

```bash
finance-lab sync-company-profiles \
  --symbols 300308.SZ 001309.SZ 920000.BJ
```

同步过程仅使用 BaoStock 与 AkShare，按股票原子缓存行业、主营、产品和主营构成；失败后重新执行即可
续跑。新闻分析仍只读取本地 `a_share_universe.csv`，不会在请求链路实时抓公司资料。免费网页源可能因
限流或字段变化暂时不可用，此时保留已有成功缓存并显式报告失败。

生成真实日报和前端 JSON 快照：

```bash
finance-lab daily-radar \
  --output reports/daily-radar.md \
  --json-output reports/daily-radar.json
```

启动本地 API（日报读取 + 单事件按需分析）：

```bash
finance-lab serve --host 127.0.0.1 --port 8000
```

另开一个终端启动前端：

```bash
cd web
corepack pnpm install
corepack pnpm dev
```

访问 `http://127.0.0.1:5173/today` 查看 Top 5，访问 `http://127.0.0.1:5173/events`
浏览最近 24 小时全部聚类事件。事件详情页可以后台生成单事件报告，并通过 Markdown 接口查看结果。
Vite 会把 `/api` 转发到本地 Python 服务；刷新按钮只重新读取最新成功快照。可通过
`http://127.0.0.1:8000/api/health` 检查 API 和快照是否可用。

`daily-radar` 同时写入 `DailyRadarSnapshot v2.1`、完整事件 catalog，以及 Top 5 的单事件分析产物。
其他可研究聚类只在用户点击“生成分析报告”后调用财报和行情证据工具；纯行情播报只展示原始聚类成员。

生成最近 24 小时的 Event-driven 日报：

```bash
finance-lab daily-radar \
  --event-cache data/event_cache/ths \
  --output reports/daily-radar.md \
  --json-output reports/daily-radar.json
```

生成一份示例热点追源报告：

```bash
finance-lab trace-news \
  --url "https://example.com/news/article" \
  --watchlist data/watchlist.example.csv \
  --output reports/demo-news-trace.md
```

也可以不用安装脚本，直接运行模块：

```bash
PYTHONPATH=src python -m finance_research_lab.cli trace-news \
  --url "https://example.com/news/article" \
  --watchlist data/watchlist.example.csv \
  --output reports/demo-news-trace.md
```

生成一份多 URL 投资雷达报告：

```bash
finance-lab radar \
  --urls "https://example.com/news/a" "https://example.com/news/b" \
  --watchlist data/watchlist.example.csv \
  --output reports/demo-opportunity-radar.md
```

生成一份包含研究任务和证据的 Agent 报告：

```bash
finance-lab research-agent \
  --url "https://example.com/news/article" \
  --watchlist data/watchlist.example.csv \
  --output reports/agent-report.md
```

## Agent v0 设计

当前版本不是自由循环的黑盒 Agent，而是一个 **代码控制的 Agent-shaped workflow**。真实 Agent 会优先输出 Agent-ready `ResearchReport`；失败时规则 fallback 会填充同一套结构：

```text
fetch_news_tool        # 获取静态 HTML 并生成 NewsItem
→ read_watchlist_tool
→ trace_news_tool      # LLM Structured Outputs 优先，规则 fallback 保底
→ render_report_tool   # 从 ResearchReport 渲染 Markdown
→ write_report_tool
```

目标 Event-driven workflow 为：

```text
discover_news_items
→ normalize_news_items
→ cluster_market_events
→ rank_hot_events
→ analyze_event_with_llm
→ map_value_chain_and_scarce_layers
→ discover_a_share_candidates
→ verify_candidates_with_tools
→ classify_impact
→ render_report
→ write_report
```

每一步都会记录成 `AgentStep`，包含：

```text
step_name
tool_name
status
summary
```

这样做的目的：

- 先把工具调用、状态记录、报告生成跑通。
- 用 JSON Schema 约束 Agent 输出，避免把自由文本直接塞进报告链路。
- 让 LLM 提出研究假设，tools 校验事实，workflow 保留可解释执行轨迹。
- 后续可以加入 `agent_runs / agent_steps` SQLite 表、RAG、A 股行情数据和回测。

Prompt 约束位于：

```text
prompts/investment_research_agent.md
```

## 热点追源模板

每条热点新闻按 7 个问题拆解：

1. **新闻类型**：资本开支、订单/合同、业绩/指引、政策落地、价格/产能变化、并购/融资、产品发布、概念炒作。
2. **谁付钱**：云厂商、政府、企业客户、消费者、交易所、协议、车企等。
3. **谁收钱**：上游材料、设备、零部件、软件/SaaS、运营商、平台、数据服务、基础设施。
4. **产业链路径**：例如 `AI CapEx -> 数据中心 -> GPU/ASIC -> 交换机 -> 光模块 -> PCB -> 液冷 -> 电力设备`。
5. **A股影响映射**：区分利多、利空、直接受益、间接受益、情绪映射和伪相关。
6. **当前阶段**：启动 / 验证 / 高潮 / 分歧 / 退潮。
7. **研究状态**：重点验证 / 进入跟踪 / 等待更多证据 / 风险偏高 / 暂不跟踪 / 伪相关排除 / 待确认。

## MVP 路线

- 产品文档：[`docs/product-spec-v0.md`](docs/product-spec-v0.md)
- 路线文档：[`docs/mvp-roadmap.md`](docs/mvp-roadmap.md)
- 模型接入、上下文控制与 Tool Calling 架构：[`docs/model-and-tooling-architecture.md`](docs/model-and-tooling-architecture.md)

```text
V0 URL 新闻追源（辅助入口）
→ V1 A股候选发现与验证
→ V1.5 证据工具与受控 Tool Calling
→ V2 自动事件发现与每日雷达
→ V3 Serenity 产业链卡点研究
→ V4 复盘与信号回测
→ V5 AI Agent 简历展示版
```

## 后续路线

### Phase 1：URL 研究辅助与证据工具

- [x] 项目骨架和 README
- [x] 示例 watchlist
- [x] 静态 HTML 新闻 URL 抓取
- [x] 热点新闻追源报告生成
- [x] 多 URL 雷达报告
- [x] A 股候选发现与 universe 校验
- [x] BaoStock 行情主源与 AkShare 公告、财报、行情 fallback
- [x] 受控 Evidence Tool Calling

### Phase 2：自动事件发现

- [x] `NewsItem` / `MarketEvent` / `Theme` 模型
- [x] 同花顺财经直播分页源和最近 24 小时原始快照
- [ ] 巨潮最新公告、全市场行情异动和官方政策 source adapters
- [x] 事件去重、聚类和热点排序
- [x] Event-driven `daily-radar.md`
- [x] 全量事件列表与单事件按需分析
- [ ] Serenity 产业链层级与供给卡点分析

### Phase 3：稳定数据源与回测验证

- [ ] Tushare 或其他稳定 provider
- [ ] 公告正文 / PDF 解析
- [ ] 涨跌幅、成交额变化、均线偏离、波动率、最大回撤
- [ ] 双均线 / 动量 / 突破等基础策略
- [ ] 手续费、滑点、调仓频率
- [ ] 年化收益、Sharpe、最大回撤、胜率
- [ ] 失败策略记录和复盘

## 风险边界

本项目只用于个人研究、学习和工程作品集展示，不构成投资建议。所有新闻、数据和市场映射都需要二次复核，尤其是社媒传闻、热点题材和已经充分发酵的交易。追源报告的重点是“看懂钱流和验证点”，不是制造追涨理由。
