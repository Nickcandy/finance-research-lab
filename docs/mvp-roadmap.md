# A股投资研究 Agent MVP 路线

> 更新时间：2026-06-30

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
→ 验证任务
→ 复盘
```

项目同时服务个人投资研究和 AI Agent 简历展示。核心不是“预测一定会涨”，而是展示如何让 LLM 提出假设、让 tools 查证事实、让 workflow 记录过程、让报告保留证据和风险。

## 路线总览

```text
V0 URL 新闻追源
→ V1 A股候选发现与验证
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
- 用 LLM Structured Outputs 或规则 fallback 生成 `ResearchReport`。
- 输出事件理解、产业链路径、股票影响、风险和验证任务。
- 记录 `AgentStep`。

边界：

- 不支持登录、付费墙和 JavaScript 动态渲染页面。
- 当前股票映射仍偏 watchlist 和关键词规则，尚未具备全 A 股候选发现能力。

## V1：A股候选发现与验证（下一步）

目标：watchlist 不再限制输出范围。系统从新闻事件出发，发现可能受影响的 A 股标的，并通过 tools 校验。

推荐流程：

```text
fetch_news_tool
→ analyze_event_with_llm
→ discover_a_share_candidates
→ verify_candidates_with_tools
→ classify_impact
→ render_report
→ write_report
```

输入：

```text
新闻 URL
watchlist CSV（可选个人上下文）
A股 universe / 查询工具
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

## V4：复盘与信号回测

目标：把研究判断变成可验证的记录。

核心问题：

```text
某条新闻触发的候选，在未来 5/10/20 个交易日表现如何？
当时的利多 / 利空 / 风险判断是否成立？
哪些类型的事件更容易变成伪相关？
```

指标：

```text
future_return_5d
future_return_10d
future_return_20d
max_drawdown_20d
win_rate_10d
avg_return
false_positive_rate
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
我做了一个 URL-first 的 A 股投资研究 Agent。系统不是让 LLM 直接荐股，而是让 LLM 提出事件假设和候选公司，再通过 tools 校验股票代码、主营、行业和市场数据。workflow 由代码控制，每一步记录 agent_steps，输出用 ResearchReport schema 约束，并保留 fallback、验证任务和复盘路径。这个项目展示了 Agent 工程里模型、工具、状态、结构化输出和可验证性的分工。
```
