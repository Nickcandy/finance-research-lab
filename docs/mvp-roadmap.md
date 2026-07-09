# A股投资研究 Agent MVP 路线

> 更新时间：2026-07-10

## 项目定位

`finance-research-lab` 的主线是 **URL-first 的 A 股投资研究 Agent**。

它从新闻 URL 或后续市场数据出发，生成可复盘的投资研究假设：

```text
新闻 URL / 市场事件
→ 事件理解
→ 产业链影响
→ A股候选发现
→ tools 校验
→ 利多 / 利空 / 情绪映射 / 伪相关
→ 证据计划
→ 公告 / 财报 / 行情 / 成交量证据
→ 验证任务
→ 复盘
```

项目同时服务个人投资研究和 AI Agent 简历展示。核心不是“预测一定会涨”，而是展示如何让 LLM 提出假设、让 tools 查证事实、让 workflow 记录过程、让报告保留证据和风险。

## 路线总览

```text
V0 URL 新闻追源
→ V1 A股候选发现与验证
→ V1.5 证据工具和多轮研究流程
→ V2 多 URL 投资雷达
→ V3 行情 / 成交量 / 财务工具
→ V4 复盘与信号回测
→ V5 AI Agent 简历展示版
```

## V0：URL 新闻追源（当前已有）

目标：输入一条静态 HTML 新闻 URL，输出一份 Markdown 研究报告。

当前能力：

- 抓取新闻标题、来源、发布时间和正文。
- 读取 watchlist 作为个人上下文。
- 读取 A 股 universe 作为候选校验数据。
- 用 LLM Structured Outputs 或规则 fallback 生成 `ResearchReport`。
- 输出事件理解、产业链路径、股票影响、风险和验证任务。
- 记录 `AgentStep`。

边界：

- 不支持登录、付费墙和 JavaScript 动态渲染页面。
- 当前股票映射仍偏关键词规则，候选发现和证据工具还在演进。

## V1：A股候选发现与验证

目标：watchlist 不再限制输出范围。系统从新闻事件出发，发现可能受影响的 A 股标的，并通过 tools 校验。

推荐流程：

```text
fetch_news_tool
→ read_watchlist_tool
→ read_a_share_universe_tool
→ analyze_event_with_llm
→ discover_a_share_candidates
→ verify_candidates_with_tools
→ classify_impact
→ render_report
→ write_report
```

输入：

```text
新闻 URL / 可信新闻源
watchlist CSV（可选个人上下文）
A股 universe / 查询工具
公司公告 / 财报摘要（V1.5+）
今天或本周的行情 / 成交量摘要（V1.5+）
```

输出分组：

```text
已校验 A股候选
待确认候选
伪相关 / 风险排除
watchlist 命中
后续验证任务
```

验收标准：

- 候选股票可以来自 watchlist 之外。
- 候选进入正式报告前必须经过 tool 校验。
- 未校验候选只能进入“待确认候选”。
- 报告明确区分利多、利空、情绪映射和伪相关。
- 所有结论保留证据、风险和验证任务。

## V1.5：证据工具和多轮研究流程（当前实施）

目标：把当前的一轮报告生成，升级成“先判断事件类型，再决定查什么证据”的多步流程。

V1.5 的验证重点不是“新闻是真是假”。后续新闻源会接入可信来源，系统要验证的是：

```text
新闻事件 -> 公司影响 -> 公告 / 财报证据 -> 行情 / 成交量反应 -> 是否值得继续跟踪
```

### 数据源选择

先按 A 股优先。V1.5 不追求一次性接完所有数据源，先做 provider adapter，再接一个最容易跑通的数据源。

推荐顺序：

```text
第一阶段：mock provider
  - 优点：不需要 token，先保证 workflow 和报告结构稳定。
  - 用途：公告、财报、行情和成交量的结构占位。

第二阶段：AkShare adapter
  - 优点：本地 Python 包，通常不需要 token，适合快速原型。
  - 用途：行情、成交量、部分财务数据。
  - 风险：底层数据源可能变化，稳定性不如正式数据服务。

第三阶段：Tushare provider
  - 优点：接口更标准，适合后续长期使用。
  - 用途：行情、财务指标、公告/日历等结构化数据。
  - 需要：Tushare token，部分高级接口可能需要权限或积分。

第四阶段：交易所 / 巨潮公告 provider
  - 优点：公告来源更接近官方披露。
  - 用途：公司公告、年报、季报、重大事项公告。
  - 风险：网页和接口稳定性、反爬、PDF 解析复杂度。
```

### 需要用户准备的东西

如果先用 AkShare：

```text
不需要 token
需要确认 Python 环境能安装 akshare
需要接受数据源稳定性一般，先用于原型验证
```

如果用 Tushare：

```text
需要注册 Tushare
需要提供 TUSHARE_TOKEN
需要确认账号能访问目标接口
```

如果直接抓巨潮 / 交易所公告：

```text
通常不需要 token
需要确认目标公告范围：A 股全部、只看 watchlist、还是只看某个行业
需要接受公告 PDF 解析会单独增加复杂度
```

V1.5 建议用户先处理这些数据：

```text
1. watchlist 里每个 symbol 保持规范：300308.SZ / 600519.SH
2. 每个公司补齐 themes、thesis、risks
3. 每个公司最好补一个 industry / sector 字段，方便做上下游
4. 先选 5-10 个重点公司做测试，不要一开始覆盖全市场
5. 如果选择 Tushare，先把 token 配到 .env：TUSHARE_TOKEN=...
```

### 事件类型

第一版支持：

```text
订单 / 合同
业绩 / 指引
政策 / 监管
涨价 / 供需变化
资本开支
产品发布
风险暴露
纯情绪题材
```

### 证据工具

```text
fetch_company_announcements(symbol, start_date, end_date)
  -> 公司公告列表

fetch_financial_reports(symbol, periods)
  -> 财报摘要、收入、利润、现金流、毛利率等核心字段

fetch_market_snapshot(symbol, lookback_days)
  -> 最近价格、涨跌幅、成交量、成交额、区间高低点
```

### 多步流程

```text
可信新闻输入
-> 读取 watchlist
-> 读取 A 股 universe
-> 判断事件类型
-> 生成证据计划
-> 查公告 / 财报 / 行情 / 成交量
-> 计算上下游 scale
-> 整理支持证据和反对证据
-> 判断股票池影响
-> 输出 Evidence-first 报告
```

### 事件类型需要的数据

```text
新闻字段：
  headline
  source
  published_at
  url
  body / summary

股票池字段：
  symbol
  name
  market
  themes
  thesis
  risks
  industry / sector

公司公告字段：
  symbol
  title
  announcement_type
  published_at
  url
  summary

财报字段：
  symbol
  report_period
  revenue
  revenue_yoy
  net_profit
  net_profit_yoy
  gross_margin
  operating_cash_flow

行情字段：
  symbol
  trade_date
  open
  high
  low
  close
  pct_chg
  volume
  amount
```

如果这些字段暂时拿不到，V1.5 允许用 mock 数据或空值，但报告里必须明确标记“待补充”。

### 上下游 scale

第一版使用 0-3 分：

```text
0：无明显关系
1：情绪映射或弱相关
2：产业链相关，但收入弹性不明确
3：直接订单、核心供应、收入弹性明确
```

这个 scale 用于：

```text
upstream_relevance_score
downstream_relevance_score
revenue_elasticity_score
```

如果“白猫大神”的 scale 指的是另一套具体评分标准，后续把原文或规则补进来再替换。

## V2：多 URL 投资雷达

目标：输入多条新闻 URL，输出每日投资研究雷达。

报告结构：

```markdown
# 今日 A股投资研究雷达 YYYY-MM-DD

## 今日核心事件
## 已校验 A股候选
## 待确认候选
## 风险排除 / 伪相关
## watchlist 命中
## 明日验证任务
## 待复盘记录
```

工程重点：

- 每条 URL 独立记录成功或失败。
- 单条失败不影响其他 URL。
- 全部失败时不生成误导性报告。
- 多条新闻提到同一股票时合并证据和风险。

## V3：行情 / 成交量 / 财务工具

目标：让候选验证不只依赖新闻和公司描述，还能接入市场状态。

第一批工具：

```text
fetch_a_share_profile(symbol)
fetch_price_snapshot(symbol)
fetch_volume_signal(symbol)
fetch_basic_valuation(symbol)
fetch_market_snapshot(symbol, lookback_days)
fetch_company_announcements(symbol, start_date, end_date)
fetch_financial_reports(symbol, periods)
```

配置项建议：

```env
STOCK_DATA_PROVIDER=akshare
STOCK_DATA_API_KEY=
STOCK_DATA_BASE_URL=
STOCK_DATA_TIMEOUT_SECONDS=30
MARKET_LOOKBACK_DAYS=5
```

第一批信号：

```text
放量上涨
放量下跌
趋势突破
高位风险
估值异常
近 20 日涨幅过大
```

输出：

```text
market_signals.csv 或 SQLite signals 表
候选股票的市场状态摘要
报告中的“价格状态 / 风险状态”
```

## V4：复盘、Agent 状态记录与信号回测

目标：把研究判断变成可验证的记录。

核心问题：

```text
某条新闻触发的候选，在未来 5/10/20 个交易日表现如何？
当时的利多 / 利空 / 风险判断是否成立？
哪些类型的事件更容易变成伪相关？
```

工具设计：

```text
read_watchlist(path) -> watchlist
fetch_market_data(date, universe) -> market_snapshot
detect_signals(market_snapshot) -> signals
trace_news(headline_or_url, watchlist) -> news_trace
rank_opportunities(signals, news_trace, watchlist) -> ranked_candidates
render_report(candidates) -> markdown
save_report(markdown) -> report_path
save_agent_run(run) -> run_id
```

核心记录：

```text
agent_runs
agent_steps
research_reports
candidates
validation_tasks
reviews
signals
```

回测指标：

```text
future_return_5d
future_return_10d
future_return_20d
max_drawdown_20d
win_rate_10d
avg_return
false_positive_rate
```

## V5：AI Agent 简历展示版

目标：把项目整理成能用于面试讲解的完整案例。

交付材料：

- README：产品定位、快速开始、示例报告。
- 架构文档：workflow、tools、LLM adapter、schema、fallback。
- 示例报告：单 URL、多 URL、候选校验、风险排除。
- 数据表设计：agent_runs、agent_steps、candidates、reviews。
- 一组复盘或回测结果。
- 面试讲稿。

推荐面试表达：

```text
我做了一个 URL-first 的 A 股投资研究 Agent。系统不是让 LLM 直接荐股，而是让 LLM 提出事件假设和候选公司，再通过 tools 校验股票代码、主营、行业、公告、财报和市场数据。workflow 由代码控制，每一步记录 agent_steps，输出用 ResearchReport schema 约束，并保留 fallback、证据计划、验证任务和复盘路径。这个项目展示了 Agent 工程里模型、工具、状态、结构化输出和可验证性的分工。
```

## 下一阶段最小开发任务

V1.5 最小版已经落地到 mock provider。下一步是把 mock provider 替换成真实数据源 adapter。

验收标准：

```text
输入 1 条可信新闻 + 股票池 + A 股 universe
先判断事件类型
生成证据计划
至少调用公司公告 / 财报工具
至少调用行情 / 成交量工具
输出 reports/agent-report.md
报告包含事件类型、证据计划、支持证据、反对证据、上下游 scale、市场反应、待验证点
pytest 通过
```

后续任务拆分：

```text
Task 1：接入 AkShare 行情 / 成交量 adapter
Task 2：接入 Tushare provider 配置和 token 读取
Task 3：接入公司公告列表 provider
Task 4：把 mock 反对证据替换成真实数据生成
Task 5：把 Evidence-first 报告接入多 URL radar
Task 6：补真实 provider 的隔离测试
```
