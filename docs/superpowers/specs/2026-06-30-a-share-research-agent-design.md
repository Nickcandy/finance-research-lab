# A股投资研究 Agent 产品边界设计

> 日期：2026-06-30

## 背景

当前项目已经实现 URL 新闻抓取、单 URL 追源报告、多 URL radar 报告、`research-agent` 任务/证据报告、Chat Completions 兼容 LLM 接入、`ResearchReport` structured output 和 `AgentStep` 记录。

原有文档仍保留了“手动新闻 + 自选股 CSV”的旧边界，容易误导后续实现。新的产品期望是：项目作为个人投资理财研究工具，可以从新闻或市场事件中判断哪些 A 股可能利多、利空或只是伪相关，不应被 watchlist 限制。

## 目标

产品定位调整为 URL-first 的 A 股投资研究 Agent。

核心目标：

1. 输入新闻 URL 或后续市场事件。
2. 分析事件类型、产业链路径和影响方向。
3. 发现可能受影响的 A 股候选，不限于 watchlist。
4. 通过 tools 校验候选公司、代码、行业、主营和证据。
5. 输出已校验候选、待确认候选、伪相关/风险排除和验证任务。
6. 作为 AI Agent 简历项目，展示 workflow、tools、schema、fallback 和 agent steps。

## 非目标

当前阶段不做：

- 自动交易。
- 确定性买卖建议。
- 港股和美股候选发现。
- 大规模爬虫、登录页、付费墙和 JavaScript 动态渲染抓取。
- 完整行情、财务、估值和回测系统。
- 自由循环的黑盒 Agent。

## 产品边界

### watchlist 语义

`watchlist` 不再是候选股票全集。

它只承担：

- 个人关注上下文。
- thesis / risks 补充。
- 命中高亮。
- 排序和复盘优先级。

候选股票可以来自 watchlist 之外。

### A股优先

第一阶段只输出 A 股候选。后续可扩展港股、美股，但不进入当前设计。

### 候选校验

LLM 可以提出候选方向和公司，但不能直接决定最终事实。

报告需要区分：

```text
已校验候选：tool 已确认公司/代码/主营或行业相关性。
待确认候选：LLM 或规则提出，但 tool 校验不足。
排除项：伪相关、证据不足、主营不匹配或风险过高。
```

## 推荐工作流

```text
fetch_news_tool
→ analyze_event_with_llm
→ discover_a_share_candidates
→ verify_candidates_with_tools
→ classify_impact
→ render_report
→ write_report
```

职责分工：

- workflow 控制步骤、失败处理和 `AgentStep` 记录。
- LLM 负责事件理解、产业链推理和候选假设。
- tools 负责新闻抓取、watchlist 读取、A 股公司查询、候选校验和报告写入。
- schema 固定核心输出，避免自由文本进入主链路。
- fallback 保证 LLM 不可用时仍能输出低置信研究线索。

## 数据模型方向

现有 `ResearchReport` 继续作为单 URL 研究报告核心契约。

后续建议扩展概念：

```text
CandidateStock
CandidateVerification
CandidateGroup
RadarReport
ReviewRecord
```

候选相关字段至少包含：

```text
symbol
name
market
industry
business_summary
impact_direction
impact_type
impact_strength
verification_status
evidence
risks
watchlist_hit
source
```

## 报告结构

单 URL 报告建议包含：

```text
事件摘要
产业链路径
已校验 A股候选
待确认候选
风险排除 / 伪相关
watchlist 命中
验证任务
风险边界
```

多 URL radar 报告建议包含：

```text
今日核心事件
已校验 A股候选
待确认候选
风险排除 / 伪相关
watchlist 命中
明日验证任务
待复盘记录
```

## 错误处理

- URL 抓取失败：记录 error step，不生成该 URL 的分析。
- LLM 失败：走规则 fallback，并标记低置信。
- tool 查询失败：候选不能进入“已校验候选”。
- 多 URL 部分失败：成功项继续输出，失败项记录在执行步骤中。
- 多 URL 全部失败：不写误导性报告。

## 测试方向

后续实现时至少覆盖：

- watchlist 之外的 A 股候选可以进入输出。
- watchlist 命中只影响高亮，不限制候选范围。
- tool 校验失败的候选进入待确认或排除项。
- LLM 失败时 fallback 仍能输出低置信报告。
- 多 URL 中单条失败不影响其他 URL。

## 面试表达

可以把项目描述为：

```text
我做了一个 URL-first 的 A 股投资研究 Agent。系统不是让 LLM 直接荐股，而是让 LLM 从新闻中提出事件假设和候选公司，再通过 tools 校验股票代码、主营、行业和后续行情状态。workflow 由代码控制，每一步记录 agent_steps，输出用 ResearchReport schema 约束，并保留 fallback、验证任务和复盘路径。这个项目展示了 Agent 工程里模型、工具、状态、结构化输出和可验证性的分工。
```
