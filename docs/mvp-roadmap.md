# 投资机会雷达 Agent MVP 路线

> 更新时间：2026-06-17

## 项目定位

`finance-research-lab` 的主线是 **市场分析与投资机会雷达 Agent**。

它不是黑盒荐股系统，也不是自动交易系统，而是：

> 新闻 / 行情 / 成交量 / 自选股 / 基本面 → 投资假设 → 支持证据与反对证据 → 动作建议 → 止损/证伪 → 复盘。

核心产物是可复盘的 Markdown 研究报告和结构化信号记录。

## MVP 演进路线

```text
V0 热点追源工具
→ V1 投资机会雷达日报
→ V2 行情/成交量信号
→ V3 信号回测
→ V4 Agent 化工具调用 + 状态记录
→ V5 作品集展示版
```

## V0：热点追源工具（当前已有）

输入一条热点新闻和股票池，输出热点追源 Markdown 报告。

当前能力：

- 读取 `data/watchlist.example.csv`；
- 识别主题和新闻类型；
- 做简单产业链映射；
- 把股票池标的分为直接受益、间接受益、情绪映射；
- 生成 Markdown 报告；
- 记录 `AgentStep`。

## V1：投资机会雷达日报（下一步）

目标：每天输出一份 `reports/YYYY-MM-DD-opportunity-radar.md`。

输入：

```text
3 条手动新闻
自选股 CSV
可选：指数/个股价格摘要
```

输出结构：

```markdown
# 今日投资机会雷达 YYYY-MM-DD

## 市场概览
## 今日热点
## 中长线观察
## 短期交易机会
## 高位不追 / 风险排除
## 明天验证点
```

动作分类：

```text
中长线观察
短期交易机会
等回调
小仓试错
只看不动
放弃
风险排除
高位不追
```

每个候选标的必须包含：

```text
核心逻辑
催化剂
支持证据
反对证据
当前价格状态
建议动作
止损/证伪条件
时间退出
复盘日期
```

## V2：行情和成交量信号

接入 AKShare / BaoStock / yfinance 之一，先做简单、可解释的信号。

第一批信号：

```text
放量上涨：pct_chg > 5%，amount > 2 × rolling_20d_amount
放量下跌：pct_chg < -5%，amount > 2 × rolling_20d_amount
趋势突破：close 突破 20 日新高
高位风险：近 20 日涨幅过大 + 成交额异常放大
```

输出：

```text
signals.csv 或 SQLite signals 表
每日异动 Markdown 报告
```

## V3：信号回测

回测问题：

> 某个信号出现后，未来 5/10/20 个交易日收益和回撤如何？

指标：

```text
future_return_5d
future_return_10d
future_return_20d
max_drawdown_20d
win_rate_10d
win_rate_20d
avg_return
median_return
```

## V4：Agent 化工具调用和状态记录

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

核心表：

```text
agent_runs
agent_steps
recommendations
signals
reviews
```

工程重点：

- workflow 由代码控制；
- LLM 负责解释、分类、总结、报告生成；
- Python 负责数据抓取、指标计算、回测；
- 每次建议都要能复盘。

## V5：作品集展示版

交付材料：

- README；
- 架构图；
- 示例报告；
- 数据表设计；
- 一组信号回测结果；
- 一个失败案例复盘；
- 面试讲稿。

简历表达：

```text
投资机会雷达 Agent：构建面向个人投资研究的 AI Agent 系统，支持热点新闻追源、产业链映射、自选股匹配、行情异动检测、Markdown 报告生成和信号回测。采用代码控制的 workflow 记录 agent_runs / agent_steps，并通过规则信号与后续收益回测验证投资假设。
```

## 明天最小开发任务

只做 V1：新增一个“投资机会雷达日报”命令。

验收标准：

```text
输入 3 条手动新闻 + 股票池
输出 reports/YYYY-MM-DD-opportunity-radar.md
报告包含热点、候选标的、风险排除、明天验证点
pytest 通过
```
