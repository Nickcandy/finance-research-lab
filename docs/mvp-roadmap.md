# A股投资研究 Agent MVP 路线

> 更新时间：2026-07-10

## 项目定位

`finance-research-lab` 的主线是 **Event-driven 的 A 股投资研究 Agent**。

它主动发现新闻、公告和行情异动，把多个来源聚合成市场事件，再生成可复盘的投资研究假设：

```text
新闻源 / 公司公告 / 行情异动
→ NewsItem 标准化
→ MarketEvent 去重与聚合
→ 热点事件排序
→ 产业链层级与供给卡点
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
→ V2 自动事件发现与每日雷达
→ V3 Serenity 产业链卡点研究
→ V4 复盘与信号回测
→ V5 AI Agent 简历展示版
```

## V0：URL 新闻追源（当前已有的辅助入口）

目标：输入一条静态 HTML 新闻 URL，输出一份 Markdown 研究报告。

这条路径用于手动深挖单个来源和调试下游研究流程，不再是目标产品的主入口。URL 后续作为 `NewsItem.source_url` 保留。

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
第一阶段：BaoStock + AkShare provider chain（当前实现）
  - BaoStock：A 股盘后日线行情主源，不复权，不需要 token。
  - AkShare：巨潮公告元数据、财务指标，以及 BaoStock 失败时的行情 fallback。
  - 风险：两者底层数据源都可能变化；fallback 失败时保留原始错误，不伪造数据。

第二阶段：Tushare provider
  - 优点：接口更标准，适合后续长期使用。
  - 用途：行情、财务指标、公告/日历等结构化数据。
  - 需要：Tushare token，部分高级接口可能需要权限或积分。

第三阶段：交易所 / 巨潮公告 provider
  - 优点：公告来源更接近官方披露。
  - 用途：公司公告、年报、季报、重大事项公告。
  - 风险：网页和接口稳定性、反爬、PDF 解析复杂度。
```

### 需要用户准备的东西

如果使用当前 BaoStock + AkShare 组合：

```text
不需要 token
需要确认 Python 环境能安装 baostock 和 akshare
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

这组 0-3 分是当前实现的相关性占位，不代表
[`muxuuu/serenity-skill`](https://github.com/muxuuu/serenity-skill) 的完整方法。Serenity 式研究应先排产业链层级和供给卡点，再排公司，并明确证据强度、反方理由和判断降级条件。该模型在 V3 直接迁移，不继续扩展这组三字段。

## V2：自动事件发现与每日雷达（下一阶段）

目标：无需用户手动输入 URL，系统主动发现最近 24 小时的热点和市场事件，输出每日投资研究雷达。

### 核心概念

```text
NewsItem：一篇新闻、一条公司公告或一次行情异动，保留 source_url
MarketEvent：多个来源去重、聚合后描述的同一件事
Theme：多个事件形成的持续研究方向
```

### 最小流程

```text
可信新闻源 / 公司公告 / 行情异动
→ 拉取最近 24 小时内容
→ 标准化 NewsItem
→ 去重并聚合 MarketEvent
→ 热点事件排序
→ 选择 Top 5 事件
→ 拆产业链和供给卡点
→ 发现并校验 A股候选
→ 输出 daily-radar.md
```

热点排序第一版使用确定性指标：

```text
来源数量
来源可信度
发布时间新鲜度
是否存在公司公告
是否出现行情 / 成交量反应
```

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

- 每个来源独立记录成功或失败。
- 单个来源失败不影响同一事件的其他有效来源。
- 同一事件的多个来源只生成一个 `MarketEvent`，同时保留全部 `source_url`。
- 全部失败时不生成误导性报告。
- 多个事件提到同一股票时合并证据和风险。

### 事件源接入顺序

四类事件源统一实现 `EventSource.fetch(since, until) -> tuple[NewsItem, ...]`，由代码维护固定
source registry。LLM 不负责随机寻找网站，只参与事件理解、聚类歧义判断和下游研究。

| 类型 | 第一版主源 | 备用 / 后续 | 职责 |
| --- | --- | --- | --- |
| 财经新闻 | 同花顺财经直播分页接口 | AkShare `stock_info_global_futu()`；`stock_info_global_cls()` 辅助确认 | 主动发现政策、涨价、订单、资本开支和产品发布 |
| 公司公告 | 巨潮资讯最新公告列表 | 现有 `stock_zh_a_disclosure_report_cninfo()` 单股验证；后续 Tushare | 发现合同、业绩预告、并购、回购和风险提示 |
| 行情异动 | 低频 AkShare `stock_zh_a_spot()` 新浪全市场快照 | 正式方案使用 Tushare `daily(trade_date=...)` | 发现放量、成交额和板块扩散信号 |
| 政策产业 | 国务院、发改委、工信部、证监会官方列表页 | 后续增加交易所和产业协会 | 发现高可信政策、标准、供给和产业变化 |

接入约束：

- AkShare `stock_info_global_ths()` 包装函数只请求第一页；底层同花顺接口支持分页。`ThsNewsSource` 每日运行一次，分页拉取最近 24 小时内容，通过 URL 和内容指纹去重，并写入 `data/event_cache/ths/YYYY-MM-DD.json` 原始快照。
- 巨潮最新公告列表负责发现，现有按 symbol 的 AkShare 巨潮接口负责候选验证，禁止为了发现事件而遍历全部 A 股。
- 新浪全市场快照只做低频原型，避免反复请求导致临时封禁；东方财富全市场接口不作为主源。BaoStock 继续只验证 Top 候选，不遍历全市场。
- 政策源分别实现轻量 HTML / JSON adapter，保留标题、发布时间、发布机构、分类、详情 URL 和正文摘要。
- 每个来源独立记录状态；单源失败不阻断其他来源，全部来源失败时不生成热点报告。

实现顺序固定为：

```text
ThsNewsSource
→ CninfoLatestAnnouncementSource
→ SinaMarketAnomalySource（后续可替换为 Tushare）
→ MiitPolicySource / NdrcPolicySource / GovPolicySource / CsrcPolicySource
```

## V3：Serenity 产业链卡点研究

目标：把热点事件转换为系统变化，先排产业链层级和真实供给卡点，再发现公司并核验证据，而不是直接从热门股票开始。

核心流程：

```text
热点事件
→ 系统发生什么变化
→ 哪个物理 / 工艺 / 产能约束变紧
→ 产业链分层
→ 稀缺层级排序
→ A股候选池
→ 公告 / 财报 / 客户 / 产能 / 行情证据
→ 优先研究名单与降级条件
```

报告至少说明：

```text
卡住的环节
产业链位置
排序原因
证据强度：Strong / Medium / Weak / Unverified
主要风险
什么情况说明判断错了
下一步验证项
```

现有行情、成交量和财务工具继续作为 V3 的证据输入：

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
STOCK_DATA_PROVIDER=baostock,akshare
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
我做了一个 Event-driven 的 A 股投资研究 Agent。系统主动发现新闻、公告和行情异动，把多个来源聚合成市场事件，再拆产业链和供给卡点、发现候选公司，并通过 tools 校验股票代码、主营、公告、财报和行情数据。workflow 由代码控制，每一步记录 agent_steps，输出用 schema 约束，并保留来源、fallback、验证任务和复盘路径。
```

## 下一阶段最小开发任务

V1.5 已接入 BaoStock 行情主源和 AkShare 公告 / 财报及行情 fallback，并采用最多三轮的受控 Tool Calling：模型只能在公告、
财报和行情工具中选择，代码校验参数、执行查询并回传结果后，再生成最终结构化报告。公告、财报
和行情查询缓存到本地。BaoStock 行情缓存位于 `data/baostock_cache/`，AkShare 缓存位于
`data/akshare_cache/`；行情缓存 TTL 为 24 小时，传入 `--refresh-evidence` 可同时强制刷新。
workflow 会补齐模型未调用的最低证据项；只有事件相关性至少为中等、同时具备非空公司证据和有效
行情证据的 A 股候选才标记为 `verified`。伪相关直接排除，低强度、纯情绪、空结果或部分失败候选
保留为 `unverified` 并写入待补充说明。

V2 自动事件发现、逐事件候选研究和证据核验闭环已经完成；下一阶段接入更多事件源并深化 Serenity 分析。

验收标准：

```text
无需用户手动输入 URL
拉取最近 24 小时的可信内容
标准化为 NewsItem
同一事件的多个来源聚合为一个 MarketEvent
排出 Top 5 热点事件
每个事件保留全部 source_url
输出 reports/daily-radar.md
单个来源失败不影响其他来源和事件
pytest 通过
```

后续任务拆分：

```text
Task 1：定义 NewsItem / MarketEvent / Theme
Task 2：接入 `ThsNewsSource`，每日分页拉取最近 24 小时内容并保存原始快照
Task 3：实现事件去重、聚类和热点排序（已完成）
Task 4：输出 Event-driven daily-radar.md（已完成）
Task 5：接入巨潮最新公告列表和全市场行情异动源
Task 6：接入政策源并加入 Serenity 产业链层级与供给卡点分析
Task 7：补公告正文 / PDF 和更稳定的数据 provider
```

### Task 3（已完成）

已实现确定性的事件去重、聚类和热点排序，可以把 `ThsNewsSource` 产出的 `NewsItem` 转换为稳定、
可解释的 Top 5 `MarketEvent`。本次没有接入新的数据源、LLM 或最终日报。

实现结果：

1. 新增 `event_clustering.py`，提供 `cluster_market_events()` 和 `rank_hot_events()`。
2. 聚类使用确定性的文本标准化、时间窗口、行情数值签名和字符 bigram 相似度，不依赖外部 NLP。
3. 热点排序优先独立来源数量，再按发布时间排序；同一来源的连续播报不重复增加热度。
4. 测试覆盖重复新闻、相似但不同事件、空 URL、多来源 URL、输入顺序和非法输入。
5. 已使用最近 24 小时 `ThsNewsSource` 数据做只读 smoke；CLI 与现有 URL workflow 保持不变。

验收标准：

- 相同事件的重复内容只生成一个 `MarketEvent`。
- 相似主题下的不同事件不会仅因共享行业词而合并。
- `MarketEvent.source_urls` 保留全部非空 URL，且顺序稳定、没有重复。
- 相同输入无论排列顺序如何，都得到相同的事件分组和 Top 5 顺序。
- 聚类和排序结果不依赖 LLM 或外部 NLP 服务。

### Task 4（已完成）

已实现无需 URL 的 `finance-lab daily-radar`，固定拉取最近 24 小时同花顺新闻，完成事件聚类、
Top 5 排序、逐事件分析、A 股候选发现和证据核验，并输出 `reports/daily-radar.md`。

实现结果：

1. 新增 `run_daily_radar_workflow()`，按代码控制事件发现、研究、校验、渲染和写入，并记录全部 `AgentStep`。
2. 新增固定日报 renderer，输出核心事件、产业链、已校验/待确认/排除候选、watchlist 和验证任务。
3. 候选只覆盖 A 股；watchlist 只提供上下文，伪相关、低强度和纯情绪映射不能进入已校验候选。
4. 公司与行情证据按股票在单次运行内复用；失败或没有事件时不创建、删除或覆盖报告。
5. 新增 `daily-radar` CLI，固定 A 股最近 24 小时，不增加 scheduler。

### TODO（本轮不做）

- LLM 语义聚类；当前聚类继续使用可复现的确定性规则。
- 巨潮最新公告、全市场行情异动等 source adapters；放在 Task 5。
- 官方政策源和 Serenity 产业链层级 / 供给卡点分析；放在 Task 6。
- 公告正文 / PDF 解析和更稳定的数据 provider；放在 Task 7。
