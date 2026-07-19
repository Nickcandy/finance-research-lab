# 成本受控的全量证据分析改版计划

## 文档状态

- 状态：Phase 1A 已实施，后续阶段待实施
- 目标版本：V2.2
- 适用入口：`daily-radar`、单事件分析
- 成本目标：DeepSeek 每日费用硬上限 10 元，正常目标 2～4 元
- 产品边界：研究辅助，不预测收益，不输出买卖、目标价或仓位

## 1. 改版目标

当前日报会抓取全部同花顺新闻，确定性聚类后保存完整事件 catalog，但只对排名前 5 的事件调用一次
LLM 深度分析。这个实现成本低，但存在两个问题：

1. Top 5 之外的新闻没有进入语义分析，可能遗漏对同一股票的支持证据或风险证据。
2. 当前报告直接读取事件正文并生成完整 `ResearchReport`，如果扩展到全量逐条调用，输入和输出都会重复，
   成本会随新闻数量线性增长。

本次改版将流程调整为：

```text
全量新闻与公告
  -> 本地规范化、去重、聚类
  -> Flash 批量提取短 Claim
  -> 本地构建公司证据账本
  -> 本地计算印证、冲突和升级优先级
  -> Pro 只深度分析重要事件
  -> 生成日报、事件详情和费用摘要
```

这里的“全量覆盖”是指所有有效、去重后的输入都进入 Claim 提取和证据账本；不要求每条输入都生成一篇
长报告。

## 2. 保留与修改范围

### 2.0 当前代码落点

- `workflow.py` 已抓取全量新闻、完成聚类并保存全部事件，但 `_analyze_market_event()` 只处理核心 Top 5。
- `research_agent.py` 当前每个深度事件调用一次 `structured_completion()` 并返回完整 `ResearchReport`。
- `ChatCompletionsClient` 已读取响应中的 input/output token，但上层尚未累计费用或执行人民币预算。
- `event_catalog.py` 已保存可回放的完整输入，适合作为 Claim 提取的起点。
- `DailyRadarSnapshot v2.1` 和前端已支持全部事件、按需分析、风险预警与研究候选，可增量升级。

### 2.1 保留

- 保留 `ThsNewsSource`、后续 CNInfo source 和统一的 `NewsItem` 输入。
- 保留 `cluster_market_events()`、`rank_hot_events()` 和完整 event catalog。
- 保留现有公司、财报、行情证据工具及候选股票校验。
- 保留 `DailyRadarSnapshot v2.1` 页面结构，实施最后阶段再升级合同。
- 保留无 API Key、模型失败和预算耗尽时的确定性 fallback。

### 2.2 修改

- 在事件聚类和完整报告之间新增“Claim 提取与证据账本”模块。
- 将单一 `LLM_MODEL` 调整为 Flash 提取模型与 Pro 深度分析模型。
- 增加按人民币计价的运行预算、调用前预留、调用后结算和降级策略。
- 深度分析输入改为事件证据包，不再简单拼接最多 12,000 字正文。
- Snapshot 和事件详情增加证据、冲突、分析层级及费用摘要。

### 2.3 本轮不做

- 不做向量数据库、知识图谱数据库或新的后台队列框架。
- 不让 LLM 自由决定是否继续调用模型。
- 不按每条新闻单独生成完整报告。
- 不把同源转载当成多份独立证据。
- 不因升级失败而删除上一份成功日报。

## 3. 目标数据模型

### 3.1 Claim：最小事实单元

Flash 只负责将输入压缩为短结构化事实，不负责写投资结论。

```python
@dataclass(frozen=True)
class Claim:
    id: str
    event_id: str
    source_item_ids: tuple[str, ...]
    subject: str
    predicate: str
    object: str
    claim_type: Literal[
        "fact", "forecast", "opinion", "risk", "denial", "market_reaction"
    ]
    direction: ImpactDirection
    time_horizon: Literal["immediate", "short", "medium", "long", "unknown"]
    affected_symbols: tuple[str, ...]
    confidence: ConfidenceLevel
    occurred_at: str
```

约束：

- Claim 必须能回溯到一个或多个 `NewsItem`。
- `fact` 与 `opinion` 必须分开，媒体判断不能伪装成已确认事实。
- 股票代码允许为空；公司身份仍由本地 A 股 universe 校验。
- 同一批请求允许返回多个输入的 Claim，但每个 Claim 必须带输入 ID。
- Flash 返回非法结构时，该批次重试一次；再次失败则走规则提取并记录 warning。

### 3.2 EvidenceLedger：按公司聚合的证据账本

```python
@dataclass(frozen=True)
class EvidenceLedger:
    symbol: str
    event_ids: tuple[str, ...]
    supporting_claims: tuple[Claim, ...]
    opposing_claims: tuple[Claim, ...]
    neutral_claims: tuple[Claim, ...]
    independent_source_count: int
    duplicate_source_count: int
    corroboration_score: int
    conflict_score: int
    confidence: ConfidenceLevel
```

账本同时保留正面和负面证据，不将 `+70` 与 `-60` 简化为一个 `+10`。最终页面可以显示“正面证据较强，
但同时存在高强度风险”，避免净值隐藏分歧。

### 3.3 SourceIdentity：判断证据是否独立

每个 `NewsItem` 增加稳定内容指纹和来源身份：

```text
item_id          = hash(source_type + canonical_url + normalized_title + published_at)
content_hash     = hash(normalized_title + normalized_body)
origin_key       = 官方公告编号，或可识别的首发来源；未知时为空
```

独立来源计数规则：

- 相同 `content_hash`：完全重复，只计一次。
- 相同 `origin_key`：视为同源转述，只增加传播度，不增加独立事实置信度。
- CNInfo、政府或交易所原文优先作为事实源；媒体摘要保留用于解释市场语境。
- 无法确认同源关系时保守计为独立，但降低来源质量，并在页面标为“来源独立性待复核”。

## 4. 模块与 seam

### 4.1 `ClaimPipeline` 深模块

外部 interface 只暴露一次批量处理：

```python
result = claim_pipeline.extract(events, budget)
```

它的 implementation 内部负责：

- 过滤不可研究内容；
- 按 10～20 条输入组批；
- 截取标题和 200～400 字有效摘要；
- 查询 `content_hash` 缓存；
- 调用 Flash；
- 校验 Claim schema；
- 重试和规则 fallback；
- 返回 Claim、warning 和 token/费用用量。

调用方不需要了解批大小、Prompt、缓存或模型重试。

### 4.2 `EvidenceLedgerBuilder` 深模块

这是纯本地计算模块：

```python
ledgers = build_evidence_ledgers(events, claims, universe)
```

它负责公司身份校验、同源合并、支持/反对分类、印证分数、冲突分数和置信度。规则必须确定、可重复，
不得让 LLM 直接给最终分数。

### 4.3 `AnalysisRouter` 深模块

```python
decisions = route_event_analyses(events, ledgers, watchlist, budget)
```

每个事件只得到以下一种决定：

- `pro`：生成完整深度报告；
- `flash`：使用 Claim 和本地账本生成简版报告；
- `deterministic`：预算不足或模型失败，仅输出本地摘要；
- `not_applicable`：纯行情等不可研究事件。

路由只根据确定性特征和剩余预算工作，不额外调用 LLM。

### 4.4 `DailyLLMBudget` 深模块

所有模型调用必须经过同一个 interface：

```python
reservation = budget.reserve(model_tier, estimated_input, max_output)
budget.settle(reservation, response.input_tokens, response.output_tokens)
```

它隐藏价格表、缓存命中价格、人民币累计用量和持久化。预算按 `Asia/Shanghai` 自然日统计，而不是每次运行
重新获得 10 元：创建预算对象时先从 usage ledger 读取当天已经结算和仍在预留的费用。调用前无法预留时禁止发出
请求，调用后优先使用 DeepSeek 返回的真实 usage；缺失字段才使用估算值。

日报主流程和用户发起的按需单事件分析必须使用同一个日期账本，否则当天第二次运行可能突破总上限。

## 5. Flash/Pro 路由规则

### 5.1 Flash 全量阶段

进入 Flash 的是全部去重、可研究的新闻和公告。输入只包含：

- 输入 ID、标题、来源、时间、来源类型；
- 200～400 字正文摘要；
- 聚类事件 ID；
- 本地已识别的公司名称与代码候选。

Flash 输出 Claim，不输出价值链长文、候选股完整推演或 Markdown。

### 5.2 Pro 升级条件

事件满足任一硬条件时进入 Pro 候选池：

- Watchlist 公司存在高强度负面或 mixed 风险；
- CNInfo/交易所重大公告，且本地规则识别为业绩、重组、处罚、重大合同、诉讼、减持或风险暴露；
- 同一公司同时存在强正面和强负面 Claim；
- 两个独立高质量来源对同一事实给出互斥描述；
- 事件影响强度高但 Claim 置信度低；
- 同一股票在 24 小时内被多个独立事件反复影响。

其余事件按以下确定性优先级排序：

```text
priority = watchlist_risk
         + official_source
         + conflict_score
         + corroboration_score
         + impact_strength
         + freshness
         + novelty
```

具体权重在实现第一阶段用固定常量，并通过测试锁定。每日最多 20～30 个 Pro 事件，但真正上限由剩余费用决定。

## 6. 费用控制

### 6.1 配置

价格不能散落在 Prompt 或 workflow 中，统一从 `.env` 读取：

```dotenv
LLM_FLASH_MODEL=deepseek-v4-flash
LLM_PRO_MODEL=deepseek-v4-pro
LLM_DAILY_BUDGET_CNY=10
LLM_FLASH_BUDGET_CNY=2
LLM_PRO_BUDGET_CNY=6
LLM_RETRY_BUDGET_CNY=1
LLM_RESERVE_BUDGET_CNY=1
LLM_USAGE_STORE=data/agent_runs.sqlite3
```

模型单价由 `DailyLLMBudget` 的 provider 价格表配置；文档中的费用估算不作为运行时价格来源。更新 DeepSeek
单价时只改一处。

### 6.2 预算顺序

1. 先为 Flash 全量 Claim 提取保留最多 2 元。
2. 再按优先级逐个预留 Pro 分析费用，最多使用 6 元。
3. 重试总计最多使用 1 元。
4. 最后 1 元为输出膨胀和价格估算误差预留，不主动消费。

任何阶段都必须满足：

```text
actual_cost + reserved_cost + next_max_cost <= 10 元
```

其中 `actual_cost` 包含上海自然日内之前所有运行和按需分析已经结算的费用。每次请求必须传递 `max_tokens`，
使最大输出费用与预留值一致；进程异常退出遗留的 reservation 需要在超时后标记为 unknown 并保守计费。

### 6.3 预算耗尽行为

- 立即停止后续 LLM 请求。
- 保留已经抓取的新闻、公告、Claim 和工具证据。
- 未进入 Pro 的事件使用 Flash Claim + 本地账本生成简版结果。
- Flash 未完成的批次使用规则提取。
- Snapshot 标记 `analysis_tier=deterministic` 和 `budget_exhausted=true`。
- 日报仍然成功落盘，并显示“部分事件未完成深度分析”。

## 7. 新工作流

`run_daily_radar_workflow()` 调整为以下顺序：

1. 抓取同花顺新闻及已接入的公告源。
2. 本地规范化、完全去重和事件聚类。
3. 写入原始 event catalog，确保后续失败仍可追溯。
4. `ClaimPipeline.extract()` 批量处理全部可研究输入。
5. `EvidenceLedgerBuilder` 按事件和公司构建账本。
6. `AnalysisRouter` 决定 Pro、Flash、deterministic 或 not applicable。
7. Pro 事件复用现有公司公告、财报和行情工具完成深度报告。
8. 非 Pro 事件生成简版事件结果，不再伪装成完整深度报告。
9. 构建 Snapshot、单事件产物和费用摘要，最后原子写入最新日报。

按需单事件分析复用同一套 Claim 和账本缓存；已有相同 `content_hash` 不重复付费。用户主动请求深度分析时仍受当天
10 元硬预算约束。

## 8. Snapshot 与前端变化

实施到阶段 5 时，将 `DailyRadarSnapshot` 升级到 `v2.2`，事件增加：

```text
analysis_tier: pro / flash / deterministic / not_applicable
supporting_claims[]
opposing_claims[]
corroboration_score
conflict_score
independent_source_count
```

运行摘要增加：

```text
usage.flash_calls
usage.pro_calls
usage.input_tokens
usage.output_tokens
usage.estimated_cost_cny
usage.budget_cny
usage.budget_exhausted
```

前端只增加三处展示：

1. 事件卡显示“Pro 深度分析 / Flash 提取 / 规则摘要”。
2. 事件详情分开展示“支持证据”和“反对/风险证据”，相互矛盾时显示冲突提示。
3. 运行审计显示本次 token、估算费用和预算耗尽状态。

现有 Loading、Success、Error、404 Empty、Retry 和候选股组件继续保留。

## 9. 分阶段实施计划

### 9.0 建议文件落点

只增加承担明确领域职责的模块，不为每个步骤创建一层包装：

```text
src/finance_research_lab/
  claims.py                 # Claim 数据合同、解析和稳定 ID
  claim_pipeline.py         # Flash 组批、缓存、重试和 fallback
  evidence_ledger.py        # 公司证据账本、印证和冲突纯计算
  analysis_routing.py       # Pro/Flash/deterministic 路由纯计算
  llm/budget.py             # 上海自然日人民币硬预算
  llm/usage_store.py        # SQLite usage 与 reservation 持久化
```

现有文件只做必要接线：

- `workflow.py`：按新顺序编排，并把同一预算对象传给 Claim 与深度分析。
- `research_agent.py`：接收事件证据包和目标模型，不自行决定 Pro 路由。
- `chat_completions_client.py`：支持调用级 `model`、`max_tokens`，返回缓存命中/未命中 token。
- `daily_radar_snapshot.py`：Phase 5 增加 v2.2 合同，不在前四阶段反复改 schema。
- `web/src/types/radar.ts`、事件卡、事件详情和运行审计：Phase 5 一次性对齐新合同。

测试与模块一一对应放在现有 `tests/`；前端继续使用现有 Vitest 目录，不引入新的测试框架。

### Phase 1A：真实用量与费用观察

修改范围：

- 新增统一的 DeepSeek 价格配置和 SQLite usage ledger。
- 让全部 CLI LLM 入口和按需单事件分析写入同一个计费账本。
- `structured_completion()` 与 `tool_completion()` 上报真实 usage 和缓存 token。
- CLI 和报告显示本次及上海自然日累计 token 与已计价费用。
- 本阶段保持现有 `LLM_MODEL`，只记录费用，不阻止请求。

验证：

- SQLite 首次建表、重复启动、并发写入和上海日期边界。
- Flash/Pro 精确计价、缺少缓存拆分的保守估算和未知模型提示。
- 模型请求、fallback 和现有报告结构保持不变。
- 计费存储失败不影响报告生成，但必须显示警告。

### Phase 1B：可配置的 10 元硬预算

在收集真实运行数据后实施：

- 新增 `DailyLLMBudget`、请求前费用预留、调用后结算和异常预留处理。
- 增加调用级 `max_tokens`，使最大输出费用可以被可靠预留。
- 已知价格的请求超过配置上限后停止调用并走确定性 fallback。
- 再根据实际费用决定 Flash、Pro、重试和安全余量的配额。

### Phase 2：Flash 批量 Claim 提取

修改范围：

- 新增 Claim schema、解析器、Prompt 和批处理模块。
- 新增基于 `content_hash` 的本地 JSON 缓存。
- 每批 10～20 条，正文摘要上限可测试，不开放为前端参数。
- 将全部可研究 event item 接入 Claim 提取。

验证：

- 成功、部分缺字段、非法 JSON、超时、单次重试和 fallback。
- 同内容次日重跑命中缓存，不发生 LLM 调用。
- 500～700 条输入能在 Flash 预算内完成或确定性降级。

### Phase 3：公司证据账本与矛盾检测

修改范围：

- 本地校验 `affected_symbols`。
- 构建支持、反对、中性三组 Claim。
- 实现同源合并、印证分数、冲突分数和置信度。
- 将账本写入独立运行产物，先不修改前端合同。

验证：

- 两篇同源转载只计一个独立来源。
- 公告与两家独立媒体同向时提高印证分。
- 同一事实正反互斥时提高冲突分，不做简单净额抵消。
- 不同时间跨度的观点不误判为事实冲突。

### Phase 4：Pro 动态路由与深度报告输入改造

修改范围：

- 实现纯确定性的 `AnalysisRouter`。
- Pro 使用事件证据包：Claim、来源关系、公司账本和已获取的公司/财报/行情证据。
- 保留现有 `ResearchReport` 输出，逐步替换 `_market_event_news()` 的长正文拼接。
- 未升级事件输出明确的 Flash 简版结果。

验证：

- Watchlist 高风险、重大公告和高冲突事件优先进入 Pro。
- 低价值转载不会消耗 Pro 预算。
- 路由顺序稳定，同一输入得到相同决定。
- Pro 失败只降级当前事件，不影响整份日报。

### Phase 5：Snapshot v2.2 与前端证据展示

修改范围：

- 升级 Python snapshot 校验与 TypeScript `RadarSnapshot` 类型。
- 展示分析层级、正反证据、冲突提示和费用摘要。
- fixture 只用于测试，真实 `/today` 继续读取本地 API。

验证：

- Python snapshot 测试覆盖新增字段和非法数据。
- 前端覆盖 Pro、Flash、deterministic、冲突和预算耗尽状态。
- typecheck、lint、Vitest、production build 全部通过。

### Phase 6：CNInfo 全量公告接入

CNInfo 放在 Claim 与预算框架完成之后接入，避免新增公告量直接放大 Pro 调用。公告与新闻统一进入 `NewsItem`，
但保留 `source_type=announcement`、公告编号和官方 URL。重大公告可以触发 Pro，普通公告仍先经 Flash 提取和本地路由。

验证：

- 公告与新闻能聚合到同一事件并保留各自来源。
- 同花顺转载公告不重复增加独立来源。
- 公告源不可用不影响同花顺日报，必须产生明确 warning。

## 10. 测试与验收

### Python

- Claim schema、批次映射、缓存和 fallback 单元测试。
- 账本的同源、印证、冲突和时间跨度测试。
- 路由优先级和预算边界测试。
- workflow 集成测试覆盖 Flash 全量、部分 Pro、全部降级和模型失败。
- 完整运行 `python -m pytest -q`、`python -m ruff check .` 和 `git diff --check`。

### 前端

- 新合同类型检查。
- 支持证据、反对证据、冲突提示和分析层级渲染测试。
- 费用正常、接近上限和预算耗尽状态测试。
- 运行 typecheck、lint、Vitest 和 production build。

### 成本验收

使用固定的 700 条新闻夹具运行：

- 每条有效新闻均被缓存命中、生成 Claim 或明确记录规则 fallback。
- Pro 事件由确定性优先级选择，不超过配置预算。
- 模拟最坏输出长度和一次重试后，总预留费用仍不超过 10 元。
- 第二次使用相同输入运行时，Flash Claim 提取调用数应接近 0。

## 11. 建议提交顺序

每个提交都应可独立测试和回退：

1. `feat: add llm usage ledger and hard cny budget`
2. `feat: extract batched claims with flash model`
3. `feat: build company evidence ledgers`
4. `feat: route important events to pro analysis`
5. `feat: expose evidence and usage in radar snapshot`
6. `feat: render corroborating and conflicting evidence`
7. `feat: ingest latest cninfo announcements`

不建议把七个阶段合并成一次大提交。Phase 1 完成后费用已经可控；Phase 2～4 完成后才真正实现“全量阅读、重点深挖”；
Phase 5 负责让用户看见这套逻辑；Phase 6 再扩大公告输入。

## 12. 完成定义

V2.2 完成必须同时满足：

- 全部有效、去重后的新闻和公告都进入 Claim 或明确 fallback。
- 同股多条信息可以显示相互印证和相互矛盾，不丢失正反两侧证据。
- Pro 只处理确定性规则选出的重要事件。
- 任何输入量和模型输出下，代码都不会突破 10 元配置上限。
- 模型、网络或预算失败时仍能产出可追溯的日报。
- 页面明确区分深度分析、Flash 提取和规则摘要，避免把不同质量的结果混为一谈。
