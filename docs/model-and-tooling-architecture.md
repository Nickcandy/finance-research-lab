# 模型接入、上下文控制与 Tool Calling 架构

> 更新时间：2026-06-30

## 结论

本项目的 Agent 设计不是“把新闻丢给 LLM 让它荐股”，而是：

```text
LLM 提出研究假设
tools 校验事实
workflow 控制流程
schema 固定输出
agent_steps 记录过程
```

这样既服务个人投资研究，也能作为 AI Agent 简历项目讲清楚工程边界。

## 当前产品边界

当前产品是 URL-first 的 A 股投资研究 Agent：

```text
新闻 URL
→ 事件理解
→ 产业链影响
→ A股候选发现
→ tool 校验
→ 研究报告
```

第一阶段只覆盖 A 股。`watchlist` 是个人上下文和排序信号，不是候选股票边界。

## 推荐分层

```text
src/finance_research_lab/
  llm/
    base.py                       # LLMClient 抽象接口
    chat_completions_client.py    # OpenAI-compatible API
    mock_client.py                # 测试用假模型
  agents/
    context.py                    # 上下文预算、prompt 拼装、压缩
    tools.py                      # ToolSpec、ToolRegistry
  tools.py                        # 确定性工具封装
  workflow.py                     # 代码控制的投资研究流程
  research_report_schema.py       # structured output schema
  report.py / radar_report.py     # Markdown 渲染
```

后续如果接 LangChain / LangGraph，应只替换 orchestrator 或 adapter，不重写业务模型和报告逻辑。

## Workflow 职责

workflow 决定研究流程怎么走，并记录每一步：

```text
fetch_news_tool
→ analyze_event_with_llm
→ discover_a_share_candidates
→ verify_candidates_with_tools
→ classify_impact
→ render_report
→ write_report
```

原则：

- 每一步都有明确输入、输出和失败状态。
- 单个 URL 失败不能伪装成成功分析。
- 多 URL 报告里，单条失败不影响其他成功项。
- 全部失败时不生成误导性报告。
- 每一步写入 `AgentStep`，后续可持久化为 `agent_steps`。

## LLM 职责

LLM 适合做解释和假设生成：

1. 摘要新闻事实。
2. 判断事件类型和主题。
3. 推导产业链影响。
4. 提出可能受影响的 A 股候选。
5. 区分利多、利空、情绪映射和伪相关。
6. 解释支持证据、反对证据和风险。
7. 生成后续验证任务。

LLM 不应该直接成为事实来源。候选股票、股票代码、行业、主营和行情状态需要 tools 校验。

## Tools 职责

tools 负责确定性或可追溯的工作：

```text
fetch_news(url) -> RawNews
read_watchlist(path) -> list[WatchlistItem]
lookup_a_share_company(query) -> CandidateCompany
verify_candidate(company, event) -> VerificationResult
fetch_price_snapshot(symbol) -> PriceSnapshot
render_report(report) -> markdown
write_report(markdown, output_path) -> path
```

第一阶段最重要的新工具是 A 股候选查询 / 校验 tool。它可以先基于本地 CSV，后续再接 AkShare、Tushare、BaoStock 或其他数据源。

候选输出必须区分：

```text
verified_candidates      # 已校验，可以进入正式报告
unverified_candidates    # 待确认，只能作为研究线索
excluded_candidates      # 伪相关、证据不足或风险排除
```

## Schema 职责

`ResearchReport` 是核心契约，但后续需要扩展候选校验语义。

推荐概念：

```text
RawNews                 # 新闻来源事实
EventAnalysis           # 事件理解
ValueChainTrace         # 产业链路径
CandidateStock          # A股候选
CandidateVerification   # tool 校验结果
StockImpact             # 利多/利空/映射分类
ValidationTask          # 后续验证任务
ResearchReport          # 单 URL 研究报告
RadarReport             # 多 URL 汇总
```

结构化输出的作用：

- 限制 LLM 输出格式。
- 让报告渲染不依赖自由文本解析。
- 让测试可以校验字段、枚举和候选分组。
- 为后续存储和回测保留稳定数据结构。

## 上下文控制

上下文不要无限塞 prompt，要分层：

```text
System prompt：角色、边界、禁止直接荐股
Task prompt：本次新闻和输出要求
News context：标题、来源、正文摘要、URL
Watchlist context：个人已关注股票和 thesis/risks
Tool results：候选校验、公司信息、行情摘要
Output schema：ResearchReport / Candidate schema
```

原则：

- 长新闻先摘要。
- watchlist 只作为个人上下文，不阻止输出其他股票。
- 工具结果要带 source 或可信度。
- 报告里要区分模型假设和 tool 校验事实。

## Fallback 策略

LLM 不可用时，系统仍可用规则 fallback 生成保底报告，但必须降低可信度：

```text
LLM 成功 + tool 校验成功：正式候选
LLM 成功 + tool 校验不足：待确认候选
LLM 失败 + 规则 fallback：规则研究线索
tool 查询失败：不能进入已校验候选
```

这样可以保证系统可运行，同时不把低置信结果包装成强结论。

## LangChain / LangGraph 什么时候接

当前阶段不急着接 LangGraph。现有 workflow 更适合测试和面试解释。

当出现以下需求时再接：

- 模型根据 tool 结果自主决定下一步。
- 候选验证需要多轮查询。
- 不同事件类型走不同分支。
- 高风险结论需要人工确认。
- 需要可恢复状态机。
- 需要新闻分析、公司分析、风控分析等多 Agent 分工。

接入时应该复用：

```text
models
tools
research_report_schema
report renderers
tests
```

不要把业务逻辑写死进某个 chain。

## 面试讲法

```text
我做了一个 URL-first 的 A 股投资研究 Agent。系统不是让 LLM 直接荐股，而是让 LLM 从新闻中提出事件假设和候选公司，再通过 tools 校验股票代码、主营、行业和后续行情状态。workflow 由代码控制，每一步记录 agent_steps，输出用 ResearchReport schema 约束，并保留 fallback、验证任务和复盘路径。这个项目展示了 Agent 工程里模型、工具、状态、结构化输出和可验证性的分工。
```

## 下一步实现顺序

1. 保持现有 URL-first workflow。
2. 新增 A 股候选数据源或本地 universe。
3. 新增 `lookup_a_share_company` / `verify_candidate` tool。
4. 扩展模型，区分已校验候选、待确认候选和排除项。
5. 更新报告渲染。
6. 补测试：watchlist 外股票、校验失败、伪相关排除、LLM fallback。
7. 再考虑行情、复盘、持久化和 LangGraph。
