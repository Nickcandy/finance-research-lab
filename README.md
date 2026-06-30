# finance-research-lab

一个面向个人投资研究和 AI Agent 作品集展示的本地研究工具。项目当前采用 URL-first 输入：从新闻 URL 或后续市场事件出发，拆解产业链影响，发现可能受影响的 A 股标的，并通过 tools 校验证据，最终生成可复盘的 Markdown 研究报告。

## 目标

`finance-research-lab` 解决五个问题：

1. **事件理解**：从新闻 URL 中提取事实，判断事件类型、主题和来源质量。
2. **产业链拆解**：分析谁付钱、谁收钱、影响路径和利多利空方向。
3. **A股候选发现**：从事件出发发现可能受影响的 A 股，不把 watchlist 当作候选边界。
4. **工具校验与报告输出**：通过 tools 校验公司、代码、主营和证据，生成 Markdown 研究报告。
5. **Agent 工程展示**：用 workflow、tools、structured output、fallback 和 agent steps 展示一个可解释的 AI Agent 雏形。

核心原则：

- 只输出研究辅助和观察框架，不直接给确定性买卖结论。
- 每条判断保留来源、规则和验证点。
- LLM 负责提出假设和解释，tools 负责校验事实，workflow 负责记录过程。
- `watchlist` 只是个人上下文、排序和复盘线索，不限制系统输出股票范围。
- 先做小而完整的本地工具，后续再扩展 A 股数据源、行情指标和回测。

## 当前 MVP

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

当前实现已经包含 `trace-news`、`radar` 和 `research-agent` 三个 CLI 入口。下一阶段会把股票映射从 watchlist 限制升级为 A 股候选发现与 tool 校验。

## 项目结构

```text
finance-research-lab/
  data/                         # 示例 watchlist / 后续本地数据缓存
  reports/                      # 生成的 Markdown 报告
  src/finance_research_lab/
    cli.py                      # 命令行入口
    models.py                   # 核心数据结构和 Agent-ready ResearchReport schema
    agent_models.py             # Agent run / step / tool result 数据结构
    tools.py                    # Agent 可调用工具封装
    workflow.py                 # 代码控制的 Agent v0 工作流
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
python -m pip install -e '.[dev]'
pytest
```

本地 LLM key 放在 `.env`，不要提交真实 key：

```env
LLM_API_KEY=your_api_key_here
LLM_MODEL=gpt-4o-mini
LLM_BASE_URL=https://api.openai.com/v1
LLM_RESPONSE_FORMAT=json_schema
LLM_TIMEOUT_SECONDS=60
```

`trace-news` 会优先尝试用兼容 OpenAI Chat Completions 的 Structured Outputs 生成严格的 `ResearchReport`。如果没有配置 key、LLM 请求失败、模型拒答、返回 JSON 解析失败或 schema 校验失败，会自动回退到本地规则 fallback，仍然生成 Markdown 报告。

`LLM_BASE_URL` 可以填写任意兼容 OpenAI Chat Completions 的服务地址；代码会请求 `{LLM_BASE_URL}/chat/completions`。不配置时默认使用 OpenAI 官方地址。

`LLM_RESPONSE_FORMAT` 控制结构化输出请求格式：

- `json_schema`：默认值，用于支持 OpenAI JSON Schema Structured Outputs 的服务。
- `json_object`：用于 DeepSeek 这类支持 JSON Output 但不支持 OpenAI `json_schema` 请求格式的服务。

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
fetch_news_tool        # 获取静态 HTML 并生成 RawNews
→ read_watchlist_tool
→ trace_news_tool      # LLM Structured Outputs 优先，规则 fallback 保底
→ render_report_tool   # 从 ResearchReport 渲染 Markdown
→ write_report_tool
```

后续 A 股候选发现会扩展为：

```text
fetch_news_tool
→ analyze_event_with_llm
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
V0 URL 新闻追源
→ V1 A股候选发现与验证
→ V2 多 URL 投资雷达
→ V3 行情/成交量/财务工具
→ V4 复盘与信号回测
→ V5 AI Agent 简历展示版
```

## 后续路线

### Phase 1：URL 研究辅助

- [x] 项目骨架和 README
- [x] 示例 watchlist
- [x] 静态 HTML 新闻 URL 抓取
- [x] 热点新闻追源报告生成
- [x] 多 URL 雷达报告
- [ ] A 股候选发现 tool
- [ ] A 股候选校验和待确认候选分组

### Phase 2：数据与信号

- [ ] AkShare / Tushare / yfinance 数据源适配
- [ ] 涨跌幅、成交额变化、均线偏离、波动率、最大回撤
- [ ] 每日 / 每周 Markdown 异动报告

### Phase 3：回测验证

- [ ] 双均线 / 动量 / 突破等基础策略
- [ ] 手续费、滑点、调仓频率
- [ ] 年化收益、Sharpe、最大回撤、胜率
- [ ] 失败策略记录和复盘

## 风险边界

本项目只用于个人研究、学习和工程作品集展示，不构成投资建议。所有新闻、数据和市场映射都需要二次复核，尤其是社媒传闻、热点题材和已经充分发酵的交易。追源报告的重点是“看懂钱流和验证点”，不是制造追涨理由。
