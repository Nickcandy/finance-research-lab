# finance-research-lab

一个面向个人投资研究和作品集展示的轻量金融研究工具。第一版不做黑盒荐股、不做自动交易，先把“股票池管理 + 热点新闻追源 + Markdown 报告”跑通。

## 目标

`finance-research-lab` 解决三个问题：

1. **股票池管理**：维护关注标的、主题、投资逻辑、风险点和跟踪状态。
2. **热点新闻追源**：把热点新闻拆成来源、传播链、产业链、市场映射和后续验证点。
3. **研究报告输出**：生成可放进 Obsidian / GitHub 的 Markdown 异动和追源报告。
4. **Agent-ready 数据契约**：用 `ResearchReport` 固定事件理解、产业链、股票影响和验证任务，后续让 Agent 填同一套结构。
5. **Agent 工作流雏形**：用 tools + workflow + agent steps 记录每次研究流程，后续可接 LLM / RAG / 回测。

核心原则：

- 只输出研究辅助和观察框架，不直接给确定性买卖结论。
- 每条判断保留来源、规则和验证点。
- 先做小而完整的本地工具，后续再扩展数据源、指标和回测。

## 第一版 MVP

```text
输入：
- data/watchlist.example.csv：关注股票池
- 一条可直接访问的静态 HTML 新闻 URL

处理：
- 抓取新闻标题、来源、发布时间和正文
- 读取股票池
- 生成新闻追源卡片
- 根据关键词做简单市场映射
- 输出 Markdown 报告

输出：
- reports/YYYY-MM-DD-news-trace.md
```

## 项目结构

```text
finance-research-lab/
  data/                         # 示例股票池 / 后续本地数据缓存
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
```

`trace-news` 会优先尝试用兼容 OpenAI Chat Completions 的 Structured Outputs 生成严格的 `ResearchReport`。如果没有配置 key、LLM 请求失败、模型拒答、返回 JSON 解析失败或 schema 校验失败，会自动回退到本地规则 fallback，仍然生成 Markdown 报告。

`LLM_BASE_URL` 可以填写任意兼容 OpenAI Chat Completions 且支持 JSON Schema Structured Outputs 的服务地址；代码会请求 `{LLM_BASE_URL}/chat/completions`。不配置时默认使用 OpenAI 官方地址。

Structured Outputs 只能约束返回结构，不能保证投资结论正确；报告仍然只用于研究辅助，需要人工复核证据和风险。

生成一份示例热点追源报告：

```bash
finance-lab trace-news --url "https://example.com/news/article" --watchlist data/watchlist.example.csv --output reports/demo-news-trace.md
```

也可以不用安装脚本，直接运行模块：

```bash
PYTHONPATH=src python -m finance_research_lab.cli trace-news --url "https://example.com/news/article" --watchlist data/watchlist.example.csv --output reports/demo-news-trace.md
```

## Agent v0 设计

当前版本不是自由循环的黑盒 Agent，而是一个 **代码控制的 Agent-shaped workflow**。真实 Agent 会优先输出 Agent-ready `ResearchReport`；失败时规则 fallback 会填充同一套结构：

```text
fetch_news_tool          # 获取静态 HTML 并生成 RawNews
→ read_watchlist_tool
→ trace_news_tool          # LLM Structured Outputs 优先，规则 fallback 保底
→ render_report_tool       # 从 ResearchReport 渲染 Markdown
→ write_report_tool
```

每一步都会记录成 `AgentStep`，包含：

```text
step_name
tool_name
status
summary
```

这样做的目的：

- 先把工具调用、状态记录、报告生成跑通；
- 用 JSON Schema 约束 Agent 输出，避免把自由文本直接塞进报告链路；
- 再往后可以加入 `agent_runs / agent_steps` SQLite 表、RAG、行情数据和回测。

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
5. **市场映射**：区分直接受益、间接受益、情绪映射和伪相关。
6. **当前阶段**：启动 / 验证 / 高潮 / 分歧 / 退潮。
7. **动作状态**：忽略 / 放观察池 / 等验证 / 等回调 / 可小仓试 / 高潮勿追。

## MVP 路线

- 产品文档：[`docs/product-spec-v0.md`](docs/product-spec-v0.md)
- 路线文档：[`docs/mvp-roadmap.md`](docs/mvp-roadmap.md)
- 模型接入、上下文控制与 Tool Calling 架构：[`docs/model-and-tooling-architecture.md`](docs/model-and-tooling-architecture.md)

```text
V0 热点追源工具
→ V1 投资机会雷达日报
→ V2 行情/成交量信号
→ V3 信号回测
→ V4 Agent 化工具调用 + 状态记录
→ V5 作品集展示版
```

## 后续路线

### Phase 1：研究辅助

- [x] 项目骨架和 README
- [x] 示例股票池
- [x] 热点新闻追源报告生成
- [ ] 接入真实新闻 URL 抓取和来源时间线
- [ ] 接入 Obsidian 关注股票池

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
