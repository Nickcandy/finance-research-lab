# 事件影响、风险预警与研究候选计划

## 产品边界

本阶段把新闻研究结果转换为可解释的事件方向、个股影响指数、Watchlist 风险预警和每日研究候选。
所有输出只用于本地研究辅助，不预测具体收益，不输出买卖、目标价、仓位，也不接入券商或自动交易。

后续如需收益概率，必须先建立 point-in-time 信号账本、1/5/20 个交易日结果标签和 walk-forward
样本外回测。LLM 只能解释信号，不直接生成收益概率。

## Task 4.3：纯个股行情识别

纯个股涨跌播报只描述行情结果，不能作为驱动原因继续做产业链分析。系统同时识别纯上涨和纯下跌，
但只过滤个股；板块、指数和商品行情暂不处理。

判定为纯行情需要同时满足：

- 标题明确描述单只股票的上涨、下跌、涨停或跌停。
- 正文仅补充价格、涨跌幅、成交额、封单、市值等行情指标。
- 标题和正文均没有调查、公告、业绩、订单、政策、事故、停产等原因事实。

纯行情事件继续保留在原始缓存、event catalog 和 `/events`，标记为 `not_applicable`，但不进入
核心 Top 5，详情页不提供分析按钮，分析 API 返回 `422 analysis_not_applicable`。同一聚类只要有一条
成员新闻提供明确原因，整个事件仍然可以分析。

未来单独增加“涨跌原因归因”分支，从价格异动反查公告、新闻和行业事件，不与当前新闻影响流程混用。

## Task 4.4：方向、指数与置信度

方向与关联类型分开：

```text
impact_type: direct / indirect / sentiment / false_positive
impact_direction: positive / negative / mixed / neutral / unknown
confidence: high / medium / low / unknown
```

旧 `impact_type=negative` 只作为兼容输入，新报告不再输出。LLM 提出方向、强度、置信度和理由，
数值指数由代码固定计算：high=80、medium=55、low=30，indirect 减 10、sentiment 减 20；
positive 为正、negative 为负、neutral 为 0，mixed、unknown 和 excluded 不计算指数。

事件包含正负候选时标记为 `mixed`，指数取有效候选均值。置信度独立展示，不参与指数计算。
规则 fallback 只识别显式方向词并保持低置信；无方向证据时必须为 `unknown`。只有新闻明确提及公司
或公司与事件处于同一产品节点时，才允许继承事件方向。

## Task 4.5：Watchlist 预警与研究候选

Watchlist 风险预警要求股票身份已验证、方向为 negative 或 mixed、相关强度为 medium 或 high，
并且事件已经完成分析。明确利空、高强度且置信度中高为 high，其余有效预警为 medium。

每日研究候选不受 Watchlist 限制，只从本次日报核心事件的已验证 A 股中选择 positive、
direct/indirect、medium/high 且指数非空的候选。同股跨事件去重并保留支持事件，依次按影响指数、
置信度、独立来源数、事件时间和标准代码排序，最多返回 10 个。

前端使用“Watchlist 风险预警”和“今日研究候选”命名，并明确研究候选不是买入建议。按需分析结果
不会中途改写当日日报，下一次 `daily-radar` 才重新生成预警和 Top 10。

## 数据合同

`DailyRadarSnapshot v2.1` 在事件和候选中增加方向、指数和置信度，并增加：

```text
alerts[]
research_candidates[]
summary.alert_count
summary.research_candidate_count
all_events[].analysis_status = not_applicable
all_events[].exclusion_reason = pure_stock_price_update
```

旧 snapshot 不增加兼容层，升级后重新运行 `daily-radar`。

