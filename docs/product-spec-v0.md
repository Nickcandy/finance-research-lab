# A股投资研究 Agent 产品文档

> 更新时间：2026-06-30

## 1. 一句话定位

`finance-research-lab` 是一个面向个人投资理财研究的本地 AI Agent 工具：从新闻 URL 或后续市场数据出发，识别事件、拆解产业链、发现可能受影响的 A 股标的，并用 tools 校验公司和证据，最终输出可复盘的 Markdown 研究报告。

它不是自动交易系统，也不是黑盒荐股工具。它的目标是辅助个人研究：

```text
新闻 URL / 市场事件
→ 事件理解
→ 产业链影响拆解
→ A股候选发现
→ tool 校验股票与主营相关性
→ 利多 / 利空 / 情绪映射 / 伪相关分类
→ 验证任务与复盘记录
```

## 2. 产品目标

当前产品同时服务两个目标：

1. **个人投资研究**：帮助用户从新闻和市场事件中快速判断哪些 A 股公司可能受益、受损、只是情绪映射，或者属于伪相关。
2. **AI Agent 简历项目**：展示一个真实可解释的 Agent 系统，而不是只写 prompt。项目要能讲清楚 workflow、tools、structured output、fallback、agent steps、后续 RAG/行情/回测扩展。

## 3. 核心原则

- **URL-first**：当前输入优先使用新闻 URL。暂不做大规模爬虫，不依赖动态页面抓取。
- **A股优先**：第一阶段只覆盖 A 股候选发现与验证，后续再扩展港股、美股。
- **watchlist 不是边界**：自选股只提供个人上下文、排序优先级和 thesis/risks，不限制系统输出范围。
- **LLM 提假设，tools 做校验**：LLM 可以提出候选公司和影响路径，但正式报告必须区分已校验候选和待确认候选。
- **研究辅助，不直接交易**：输出是研究状态、证据、风险和验证任务，不给确定性买卖结论。
- **可复盘**：每条判断都要保留来源、理由、证据、风险和后续验证点。

## 4. 第一阶段输入

### 4.1 新闻 URL

当前优先输入是一条或多条可直接访问的静态 HTML 新闻 URL：

```bash
finance-lab trace-news \
  --url "https://example.com/news/article" \
  --watchlist data/watchlist.example.csv \
  --output reports/demo-news-trace.md
```

```bash
finance-lab radar \
  --urls "https://example.com/news/a" "https://example.com/news/b" \
  --watchlist data/watchlist.example.csv \
  --output reports/demo-opportunity-radar.md
```

限制：

- 页面必须能直接 GET 到 HTML。
- 暂不支持登录、付费墙、反爬限制和 JavaScript 动态渲染。
- 抓取失败时应记录失败 step，不把不完整内容伪装成分析结果。

### 4.2 watchlist CSV

`data/watchlist.example.csv` 继续保留，但语义调整为“个人上下文”，不是候选股票全集。

字段：

```text
symbol,name,market,themes,thesis,risks
```

用途：

- 命中自选股时在报告中高亮。
- 给 LLM 和规则提供个人已知 thesis/risks。
- 影响排序和复盘优先级。
- 后续记录用户是否真的持续跟踪该标的。

### 4.3 A股候选查询工具

第一阶段产品设计需要补一个 A 股查询 tool。它可以先是本地 CSV，也可以后续接外部数据源。

目标输出：

```text
symbol
name
market
industry
business_summary
concepts / themes
source
```

## 5. 第一阶段输出

输出 Markdown 研究报告，分为三类结果：

1. **已校验 A股候选**：公司和代码存在，主营/行业/概念与事件有可解释关系。
2. **待确认候选**：LLM 或规则提出了可能相关公司，但工具未能充分校验。
3. **排除项 / 伪相关**：名字相似、概念蹭热点、主营关系弱、证据不足或风险明显。

单条候选至少包含：

```text
股票代码与名称
市场：A股
影响方向：利多 / 利空 / 中性 / 待判断
影响类型：direct / indirect / sentiment / negative / false_positive
影响强度：high / medium / low / unknown
核心逻辑
支持证据
反对证据或风险
是否命中 watchlist
验证任务
```

## 6. Agent 工作流

当前项目不追求自由循环的黑盒 Agent，而是采用代码控制的 Agent workflow：

```text
fetch_news_tool
→ analyze_event_with_llm
→ discover_a_share_candidates
→ verify_candidates_with_tools
→ classify_impact
→ render_report
→ write_report
```

工程分工：

- **workflow**：控制流程顺序、错误处理和 agent step 记录。
- **LLM**：理解新闻、提出产业链影响、生成候选假设、解释利多利空。
- **tools**：抓取 URL、读取 watchlist、查询 A 股公司、校验主营/行业/概念、写报告。
- **schema**：固定输出结构，避免自由文本直接进入核心链路。
- **fallback**：LLM 不可用时，使用本地规则生成保底报告，但要标注可信度限制。

## 7. 风险边界

报告不能把研究判断包装成确定性买卖建议。推荐使用这些状态词：

```text
重点验证
进入跟踪
等待更多证据
风险偏高
暂不跟踪
伪相关排除
待确认
```

避免把产品核心字段命名为：

```text
买入
卖出
小仓试错
止损价
保证收益
```

如果需要表达交易相关内容，应放在“用户自行决策参考”的研究备注里，并明确需要二次验证。

## 8. 当前已实现与缺口

已实现：

- URL 静态 HTML 抓取。
- `trace-news` 单 URL 研究报告。
- `radar` 多 URL 雷达报告。
- `research-agent` 任务规划和证据报告雏形。
- `ResearchReport` structured output 契约。
- Chat Completions 兼容 LLM 接入和本地 fallback。
- `AgentStep` 过程记录。

尚未实现：

- A 股候选发现 tool。
- A 股公司校验数据源。
- 候选分为“已校验 / 待确认 / 排除项”的正式报告结构。
- 行情、成交量、财务、估值数据。
- 持久化 agent_runs / agent_steps / reviews。
- 回测和复盘闭环。

## 9. 下一步最小任务

下一步不再围绕“手动新闻 + 自选股全集”推进，而是做：

```text
URL 新闻
→ A股候选发现
→ tool 校验
→ 标记 watchlist 命中
→ 输出已校验候选 / 待确认候选 / 排除项
```

验收标准：

- 输入一条可访问新闻 URL。
- 系统能提出 A 股候选，并记录候选来源。
- 候选必须经过 tool 校验；校验不足不能进入“已校验候选”。
- watchlist 命中只影响高亮和上下文，不限制输出。
- 报告仍然明确“不构成投资建议”。
