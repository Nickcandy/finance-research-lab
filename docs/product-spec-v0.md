# 投资机会雷达 Agent V0 产品文档

> 更新时间：2026-06-17

## 1. 一句话定位

投资机会雷达 Agent 是一个面向个人投资研究的本地工具：用 Python 获取和计算数据，用大模型整理新闻与产业链逻辑，最终输出可复盘的投资假设和风险边界。

它不是自动交易系统，也不是简单喊买卖点，而是：

```text
新闻 / 公告 / 行情 / 成交量 / 基本面 / 自选股
→ 事件识别
→ 产业链映射
→ 候选标的筛选
→ 支持证据与反对证据
→ 动作建议
→ 止损/证伪/复盘
```

## 2. 第一版先做什么

V0 只做一个能跑通的闭环：

```text
输入：3 条手动新闻 + 自选股 CSV
处理：追源、分类、映射、打标签
输出：一份 Markdown 投资机会雷达报告
```

第一版先用手动新闻，先把研究流程和报告质量跑通。新闻自动抓取、真实行情、回测、数据库放到后面。

## 3. 第一版输入

### 3.1 新闻输入

可以先是命令行参数或文本文件：

```text
1. 国常会提出推进人工智能基础设施建设
2. 某云厂商提高 AI 数据中心资本开支指引
3. 稳定币监管框架继续推进，支付基础设施受关注
```

每条新闻字段：

```text
headline: 新闻标题
source: 来源，可先写 manual / x / 财联社 / 证券时报
published_at: 发布时间，可选
url: 原文链接，可选
summary: 手动摘要，可选
```

### 3.2 自选股输入

继续使用当前项目里的：

```text
data/watchlist.example.csv
```

字段至少包括：

```text
symbol,name,market,themes,thesis,risks
```

## 4. 第一版输出

输出文件：

```text
reports/YYYY-MM-DD-opportunity-radar.md
```

报告结构：

```markdown
# 今日投资机会雷达 YYYY-MM-DD

## 1. 今日核心结论

## 2. 热点事件追源

## 3. 产业链映射

## 4. 中长线观察

## 5. 短期交易机会

## 6. 高位不追 / 风险排除

## 7. 明天验证点

## 8. 待复盘记录
```

## 5. Agent 应该做成什么样

第一版不是让大模型完全自由地“荐股”。更稳妥的结构是：

```text
Python workflow 控制流程
Python tools 负责读取数据、计算信号、保存报告
LLM 负责理解新闻、分类事件、解释产业链、写报告
```

### 5.1 第一版 workflow

```text
read_watchlist_tool
→ read_news_input_tool
→ trace_news_tool
→ map_watchlist_tool
→ rank_opportunities_tool
→ render_report_tool
→ write_report_tool
```

### 5.2 第一版工具

```text
read_watchlist(path) -> watchlist
read_news_input(path_or_args) -> news_items
trace_news(news_items) -> traced_events
map_watchlist(traced_events, watchlist) -> candidate_mappings
rank_opportunities(candidate_mappings) -> opportunity_cards
render_report(opportunity_cards) -> markdown
write_report(markdown, output_path) -> report_path
```

## 6. 大模型负责什么

LLM 适合做解释型任务：

1. 新闻摘要；
2. 判断事件类型：政策、订单、业绩、产业趋势、涨价、监管、风险暴露；
3. 推导产业链影响；
4. 区分直接受益和蹭概念；
5. 整理支持证据和反对证据；
6. 输出 Markdown 报告；
7. 后续复盘时解释当初判断哪里对、哪里错。

## 7. Python 负责什么

Python 负责确定性任务：

1. 读取 CSV / YAML / SQLite；
2. 调数据源接口；
3. 清洗行情字段；
4. 计算涨跌幅、成交额、均线、回撤；
5. 检测放量上涨、趋势突破等规则信号；
6. 做 5/10/20 日收益回测；
7. 保存 agent_runs、agent_steps、recommendations、reviews。

## 8. 基础数据需要哪些

### V0 必需

```text
自选股：symbol、name、themes、thesis、risks
新闻：headline、source、summary/url
```

### V1 增加

```text
行情：date、open、high、low、close、volume、amount、pct_chg
```

### V2 增加

```text
基本面：行业、市值、PE/PB/PS、营收增速、利润增速、ROE、现金流
```

### V3 增加

```text
历史建议：推荐日期、动作、理由、风险、价格、复盘日期、后续收益
```

## 9. 动作建议分类

输出不要只有买/卖。第一版使用这些动作：

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

每个候选标的都必须包含：

```text
股票/方向：
类型：中长线 / 事件驱动 / 短线交易
核心逻辑：
催化剂：
支持证据：
反对证据：
当前价格状态：
建议动作：
止损/证伪条件：
时间退出：
复盘日期：
```

## 10. 第一版开发任务

### Task 1：新闻输入文件

新增：

```text
data/news.example.yaml
```

包含 3 条手动新闻。

### Task 2：机会雷达数据模型

新增模型：

```text
NewsItem
TracedEvent
OpportunityCard
OpportunityRadarReport
```

### Task 3：日报 workflow

新增命令：

```bash
finance-lab radar \
  --news data/news.example.yaml \
  --watchlist data/watchlist.example.csv \
  --output reports/demo-opportunity-radar.md
```

### Task 4：报告渲染

生成 Markdown 报告，包含热点、候选标的、风险排除、明天验证点。

### Task 5：测试

至少覆盖：

```text
能读取新闻 YAML
能读取股票池
能生成 OpportunityCard
能写出 Markdown 报告
workflow 步骤数正确
```

## 11. 暂时先放后面的能力

这些能力重要，但放到 V1/V2：

```text
自动抓新闻
AKShare/Tushare 行情接入
财务指标
SQLite 落库
回测
Web UI
定时任务
```

## 12. 面试/作品集讲法

```text
我做了一个投资机会雷达 Agent。第一版不是黑盒预测股票，而是把新闻事件、自选股、产业链和行情信号组织成可复盘的投资假设。系统用 Python 做数据读取、信号计算和报告保存，用 LLM 做新闻理解、产业链映射和研究报告生成。每条建议都有支持证据、反对证据、止损/证伪条件和复盘日期，后续再用回测验证信号有效性。
```
