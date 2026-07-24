# 全量新闻事件评分实施计划与分段提示词

## 文档状态

- 状态：待实施
- 依赖设计：
  - [`full-news-impact-scoring-design.md`](full-news-impact-scoring-design.md)
  - [`cost-aware-evidence-pipeline-plan.md`](cost-aware-evidence-pipeline-plan.md)
- 当前 Snapshot：`DailyRadarSnapshot v2.1`
- 目标 Snapshot：`DailyRadarSnapshot v2.2`
- 本轮暂不实现：LLM 人民币硬预算

## 1. 结论

建议分 **7 个阶段**实施，每个阶段独立测试、独立评审、独立提交：

| 阶段 | 目标 | 主要产物 | 是否改变当前日报行为 |
| --- | --- | --- | --- |
| 1 | 评分合同与纯计算内核 | 新数据合同、评分公式、分级规则 | 否 |
| 2 | 全量 Flash Claim 提取 | 批处理、缓存、重试、规则 fallback | 否 |
| 3 | 证据账本与影响评估 | 去重、冲突、特征、三套分数 | 否 |
| 4 | 全量路由接入日报 | 移除固定 Top 5 深挖，按层级处理 | 是 |
| 5 | Snapshot v2.2 与报告 | 新字段、后端校验、Markdown 分区 | 是 |
| 6 | 前端展示 | 重大事件、重点股票、待核验、breakdown | 是 |
| 7 | Point-in-time 与回放验收 | 历史信号、确定性回放、全链路测试 | 是 |

不要直接从阶段 4 开始删除 `workflow.py` 中的 `[:5]`。当前系统虽然只深度研究 5 个事件，但已经抓取、聚类并保存
全量事件。若先删除限制，会让现有完整 `ResearchReport`、公司证据工具和 LLM 调用直接放大到全量。

现有 `llm/usage.py` 继续记录实际 token 和费用，但本轮不实现请求前预算预留、人民币硬上限或因预算耗尽触发的
降级。未来需要费用封顶时，再单独实施 `cost-aware-evidence-pipeline-plan.md` 中的预算阶段。

## 2. 当前实现基线

当前链路为：

```text
ThsNewsSource.fetch()                  全量抓取
→ cluster_market_events()             全量聚类
→ rank_hot_events(..., limit=全量)     全量排序
→ is_market_event_researchable()
→ [:5]                                固定保留 5 个
→ _analyze_market_event()             完整研究和证据工具
→ DailyRadarSnapshot v2.1
```

关键事实：

- 固定 5 个限制位于 `src/finance_research_lab/workflow.py` 的 `run_daily_radar_workflow()`。
- `event_catalog.py` 和 Snapshot 的 `all_events` 已经保留全量事件目录。
- `impact_scoring.py` 仍使用 `high / medium / low` 映射成简单分数，不满足新设计。
- 当前没有 `Claim`、`EvidenceLedger`、`ImpactAssessment`、`analysis_tier` 或 `scoring_version` 运行时代码。
- `llm/usage.py` 已记录实际 token 和费用；本轮保留记录能力，不增加硬预算。
- `ResearchReport` 是现有深度分析合同，不能用它伪装 Flash 或 deterministic 结果。

## 3. 执行纪律

每次只执行一个阶段。进入下一阶段前必须满足：

1. 本阶段定向测试通过；
2. 全量 Python 测试通过；
3. Ruff 通过；
4. `git diff --check` 通过；
5. 人工确认 diff 没有进入下一阶段；
6. 上一阶段合同已经稳定。

统一验证命令：

```bash
.venv/bin/pytest -q
.venv/bin/ruff check src tests
git diff --check
git status --short
```

每段提示词都要求 Agent：

- 先阅读两份依赖设计文档和本阶段涉及的现有代码；
- 先写失败测试，再做最小实现；
- 不修改无关代码；
- 不提前实现后续阶段；
- 不提交、不推送，除非用户在当次对话明确要求；
- 完成后停止并报告修改、测试结果、遗留问题和建议 commit message。

## 4. 阶段 1：评分合同与纯计算内核

### 4.1 范围

新增或扩展：

- `FeatureScore`
- `QuantitativeFact`
- `Claim`
- `EventImportanceFeatures`
- `StockImpactFeatures`
- `ConfidenceFeatures`
- `ImpactAssessment`
- `SCORING_VERSION`
- 事件重要度、股票影响幅度、置信度、方向、冲突、优先级和分析层级的纯计算函数

这一阶段不接入 `workflow.py`，不修改 Snapshot，不调用 LLM 或外部工具，也不删除旧
`stock_impact_score()`。

### 4.2 验收

- 所有特征只能是 `0..100` 的整数；
- 每个特征使用 `FeatureScore(value, reason_codes, evidence_refs)` 保存分数、原因和证据；
- 三套总分严格使用设计文档权重；
- 所有加权分使用 `ROUND_HALF_UP`；
- 正负影响分别保存，不做净额；
- `verify_first / critical / high / medium / low` 规则可确定性复现；
- `analysis_tier` 由代码决定；
- 每个分数都带 reason codes 和证据引用；
- 旧测试全部继续通过。

### 4.3 可复制提示词

```text
请实施“全量新闻事件评分”的阶段 1：评分合同与纯计算内核。

工作目录：
/Users/nickcandy/Desktop/workspace/finance-research-lab

开始前必须完整阅读：
1. docs/full-news-impact-scoring-design.md
2. docs/cost-aware-evidence-pipeline-plan.md
3. src/finance_research_lab/models.py
4. src/finance_research_lab/impact_scoring.py
5. tests/test_impact_scoring.py

目标：
- 增加 FeatureScore、QuantitativeFact、Claim、EventImportanceFeatures、StockImpactFeatures、
  ConfidenceFeatures、ImpactAssessment 和固定 SCORING_VERSION。
- 实现事件重要度、股票正负影响幅度、证据置信度、冲突、方向、priority_level、
  analysis_tier 的纯计算函数。
- FeatureScore 必须将 value、reason_codes 和 evidence_refs 强绑定。
- 所有加权分采用 ROUND_HALF_UP，不使用 Python 内置 round() 的银行家舍入。
- 精确采用设计文档中的权重、阈值、缺失上限和硬升级规则。
- 所有输出必须可解释，保存 reason_codes 和证据引用。

约束：
- 先写失败测试，再写最少实现。
- 优先新建职责单一的评分模块，不要把 models.py 或现有 impact_scoring.py 膨胀成巨型文件。
- 不接入 workflow.py。
- 不修改 DailyRadarSnapshot 2.1。
- 不调用 LLM、工具或网络。
- 不删除或改变现有 stock_impact_score() 的行为，避免提前破坏旧页面。
- 不实现 ClaimPipeline、EvidenceLedger、路由或前端。
- 不做无关重构。

至少覆盖测试：
- 特征越界拒绝；
- 三套公式的精确边界；
- ROUND_HALF_UP 的 .5 边界；
- positive / negative / mixed / unknown；
- verify_first、critical、high、medium、low；
- Watchlist 负面硬升级；
- 官方重大公告硬升级；
- scoring_version 固定；
- 相同输入输出完全一致。

完成后运行：
.venv/bin/pytest -q tests/test_impact_scoring.py <本阶段新增测试文件>
.venv/bin/pytest -q
.venv/bin/ruff check src tests
git diff --check

完成后停止，不进入阶段 2，不 commit、不 push。请汇报：
1. 修改文件；
2. 数据合同和公开函数；
3. 测试结果；
4. 未实现内容；
5. 建议 commit message：feat: add impact scoring contracts and kernel
```

## 5. 阶段 2：全量 Flash Claim 提取

### 5.1 范围

实现一个独立 `ClaimPipeline`：

```text
MarketEvent / NewsItem
→ stable item id
→ content_hash / origin_key
→ cache lookup
→ batch
→ Flash structured extraction
→ schema validation
→ one retry
→ deterministic fallback
→ ClaimPipelineResult
```

本阶段只实现和测试管线，不接入日报主 workflow。

### 5.2 Flash 运行时提示词骨架

Flash 只提取原文事实，不做投资结论和最终评分。工具通过模型 API 的 `tools` 字段传递，不把工具定义拼进这段
system message；本阶段默认不向 Flash 开放工具。

```text
你是 A 股新闻事实抽取器。你的任务是把一批 NewsItem 转换成可追溯 Claim。

必须遵守：
1. 只能使用输入正文中的信息，不得补造数字、日期、主体、证券代码或因果关系。
2. 每个 Claim 必须引用一个或多个 source_item_id。
3. 金额、比例、数量、周期必须写入 quantitative_facts，并保留原始单位和 source_item_id。
4. 媒体判断、预测、传闻必须分别标记为 opinion、forecast 或 risk，不能伪装为 fact。
5. affected_symbols 只输出原文明确出现的代码；只有公司名时保留 subject，不猜证券代码。
6. 不输出事件重要度、股票影响分、置信总分、目标价、收益概率或仓位建议。
7. 无法确定时使用 unknown 或空数组，不要猜。
8. 只返回符合给定 JSON Schema 的 JSON，不要返回 Markdown。
```

### 5.3 验收

- 每个输入都有成功 Claim 或明确 fallback/warning；
- 非法 JSON 最多重试一次；
- 同 `content_hash` 再次运行命中缓存；
- 批次内每个 Claim 都能映射回输入；
- 数字不能丢失来源；
- 不生成最终投资分数。

### 5.4 可复制提示词

```text
请实施“全量新闻事件评分”的阶段 2：全量 Flash Claim 提取。

工作目录：
/Users/nickcandy/Desktop/workspace/finance-research-lab

开始前必须阅读：
1. docs/full-news-impact-scoring-design.md 的第 3、5、9、12、13、17 节
2. docs/cost-aware-evidence-pipeline-plan.md 的第 3.1、4.1、5.1、7、9 节，忽略其中预算实现
3. 阶段 1 新增的 Claim / QuantitativeFact 合同
4. src/finance_research_lab/llm/chat_completions_client.py
5. src/finance_research_lab/research_report_schema.py 的严格解析风格
6. src/finance_research_lab/event_catalog.py

目标：
- 实现 stable NewsItem ID、content_hash、origin_key 和本地 Claim 缓存。
- 实现 Claim JSON Schema、严格解析、批处理、Flash 调用、一次重试和 deterministic fallback。
- 返回结构化 ClaimPipelineResult：claims、warnings、每批状态、cache hits 和 fallback 数量。
- 把本文档“Flash 运行时提示词骨架”落实为稳定 system prompt；user 消息只放批次 JSON payload。

约束：
- 先写失败测试。
- 不依赖聊天历史；每个请求必须携带完整 schema 所需的输入 ID、标题、正文、来源、发布时间和来源类型。
- 不把最终评分规则写进 Prompt。
- 不允许 LLM 补造原文没有的数字或证券代码。
- 缓存写入使用原子替换；缓存损坏必须告警并安全重算。
- 单批失败不能丢掉整日其他输入。
- 默认不向 Flash 开放 tools。
- 不接入 run_daily_radar_workflow。
- 不实现 EvidenceLedger、Pro 路由、Snapshot 或前端。

至少覆盖：
- 正常多输入多 Claim；
- 输入和 Claim 映射；
- 原文数字及单位回溯；
- 非法 JSON 一次重试；
- 第二次失败走规则 fallback；
- 超时；
- 部分批次失败；
- cache hit；
- cache 损坏；
- content_hash 去重；
- 相同输入得到稳定 Claim ID。

完成后运行定向测试、全量 pytest、Ruff 和 git diff --check。

完成后停止，不进入阶段 3，不 commit、不 push。汇报批大小策略、缓存格式、fallback 行为、测试结果和未实现内容。
建议 commit message：feat: extract batched news claims
```

## 6. 阶段 3：证据账本与影响评估

### 6.1 范围

实现：

- `SourceIdentity`
- `EvidenceLedger`
- 同源转载和独立来源判断
- 事件特征推导
- 股票影响特征推导
- 置信特征推导
- 同方向证据聚合
- 正负证据分离
- 强冲突识别
- `ImpactAssessment`

本阶段用固定 fixture 和本地 company universe 测试，不调用真实外部 Provider，不接入 workflow。

### 6.2 验收

- 重复转载不提高幅度或置信度；
- 第二、第三个高质量独立来源奖励封顶；
- 未验证股票不能进入正式重点候选；
- 数字缺失会触发特征上限；
- 订单、业绩、风险、政策等规则至少各有边界测试；
- 同股正负证据不被平均或抵消；
- `ImpactAssessment` 完全由代码计算。

### 6.3 可复制提示词

```text
请实施“全量新闻事件评分”的阶段 3：证据账本与影响评估。

工作目录：
/Users/nickcandy/Desktop/workspace/finance-research-lab

开始前必须阅读：
1. docs/full-news-impact-scoring-design.md 第 6～10、12、13、17 节
2. docs/cost-aware-evidence-pipeline-plan.md 第 3.2、3.3、4.2 节
3. 阶段 1 的评分内核
4. 阶段 2 的 ClaimPipelineResult
5. src/finance_research_lab/a_share_universe.py
6. src/finance_research_lab/models.py 中公司、公告、财务和行情合同

目标：
- 实现 SourceIdentity 和 EvidenceLedger。
- 按 origin_key/content_hash 识别转载与独立来源。
- 从 Claim、MarketEvent、本地 A 股 universe 和已有工具证据推导三组 feature。
- 使用阶段 1 纯函数生成 ImpactAssessment。
- 支持订单、业绩、回购/减持/控制权、风险、资本开支、商品价格、政策、产品获批八类规则。
- 对缺失分母、身份未验证、来源冲突和量化不完整执行设计中的降级与上限。

约束：
- 先写失败测试。
- 分数必须由代码计算，LLM 只提供 Claim。
- 同一转载不能重复加分。
- positive_magnitude 和 negative_magnitude 分开。
- 不能用简单平均聚合同股跨事件影响。
- 不能把媒体“超预期”当成事实，除非存在可验证基准。
- 工具数据缺失必须降低 confidence 或特征上限，不能补默认好分。
- 不调用真实网络 Provider。
- 不接入 workflow、Snapshot 或前端。

至少覆盖：
- 同源转载；
- 两个独立官方/高质量来源；
- 正负证据并存；
- 订单金额/TTM 营收各档边界；
- 框架协议降级；
- 业绩缺少预期基准；
- 控制权和核心资质硬升级；
- 政策征求意见与正式生效差异；
- 未验证证券代码；
- 工具证据缺失；
- 同股跨事件保留 max positive/max negative；
- 相同输入和 scoring_version 确定性一致。

完成后运行定向测试、全量 pytest、Ruff 和 git diff --check。

完成后停止，不进入阶段 4，不 commit、不 push。汇报证据独立性规则、八类事件规则覆盖、测试结果和未实现内容。
建议 commit message：feat: assess event and stock impact evidence
```

## 7. 阶段 4：AnalysisRouter 与全量日报接入

### 7.1 目标链路

```text
全量 NewsItem
→ 全量 MarketEvent
→ 全量 Claim 或 fallback
→ 全量 EvidenceLedger
→ 全量 ImpactAssessment
→ AnalysisRouter
   ├─ pro              复用现有 _analyze_market_event() 和证据工具
   ├─ flash            Claim + ledger 简报
   ├─ deterministic    规则摘要
   └─ not_applicable   只保留目录
```

固定 Top 5 在这一阶段才移除。所有 `critical / verify_first / high` 事件进入 Pro，不再由位置切片或预算控制。

### 7.2 Pro 运行时提示词边界

Pro 可以使用工具，但最终分数仍由代码计算。发送给模型的上下文只包含当前事件：

```text
system:
你是 A 股事件证据分析器。请基于当前事件的 Claim、来源关系、公司身份、公告、财务和行情证据，
输出事件解释、价值链关系、候选公司关系、支持证据、反对证据、风险和待验证问题。
不得输出最终 event_importance、impact magnitude、confidence 总分、收益概率、目标价或仓位建议。
不得使用未出现在输入或工具结果中的事实。

user:
当前 event_id、Claim、SourceIdentity、EvidenceLedger、已验证公司候选、已有证据和缺口的 JSON。

tools:
通过模型 API 的 tools 字段提供白名单工具定义。

assistant tool_call:
只调用当前证据缺口所需工具。

tool:
追加结构化 ToolResult，并保留 tool_call_id。
```

不同事件之间不共享对话历史。可以共享本地缓存，但不能把上一事件的 messages 传给下一事件。

### 7.3 验收

- 全部可研究事件都有 Claim/assessment/route；
- 不再固定只分析 5 个；
- 低价值转载不触发 Pro；
- `verify_first` 优先核验；
- Pro 失败只降级当前事件；
- 纯行情事件继续 `not_applicable`；
- 同一公司证据缓存可复用，但 event messages 隔离。

### 7.4 可复制提示词

```text
请实施“全量新闻事件评分”的阶段 4：AnalysisRouter 与全量日报接入。

工作目录：
/Users/nickcandy/Desktop/workspace/finance-research-lab

开始前必须阅读：
1. docs/full-news-impact-scoring-design.md 第 4、10～13、17、18 节
2. docs/cost-aware-evidence-pipeline-plan.md 第 4.3、5～7、9 节
3. 阶段 1～3 的公开合同
4. src/finance_research_lab/workflow.py 的 run_daily_radar_workflow() 和
   _analyze_market_event()
5. src/finance_research_lab/evidence_tool_agent.py
6. tests/test_daily_radar.py

目标：
- 新增纯计算 AnalysisRouter。
- 把 ClaimPipeline、EvidenceLedgerBuilder、ImpactAssessment 和 router 接入 daily-radar。
- 移除“排序后固定 [:5] 深度分析”，改为全量廉价评估、按 priority/tier 深挖。
- Pro 复用现有深度分析和工具；Flash 使用 Claim/ledger 生成简版结果；deterministic 使用规则摘要；
  not_applicable 只保留目录。
- 同一天共享证据缓存，不同事件的 LLM messages 完全隔离。
- 记录每个事件的 analysis_tier、route reason、fallback 和 warning。

约束：
- 先改写现有 Top 5 测试，使它表达新目标，再实现。
- 不让全部事件都进入 _analyze_market_event()。
- 不用 LLM 最终分决定路由。
- Pro 失败只降级当前事件，不中止整份日报。
- verify_first 先调用原始公告/财报/政策证据核验，再决定是否升级。
- 保留现有 event catalog 和按需单事件分析能力。
- 不在本阶段升级 Snapshot schema 或修改前端；可以新增内部运行结果合同供阶段 5 使用。
- 不做无关重构。

至少覆盖：
- 6 个事件全部被 Claim/score，只有满足规则者进 Pro；
- 高影响低置信进入 verify_first；
- 低价值转载不进 Pro；
- Watchlist 高风险优先；
- Flash 失败降级 deterministic；
- 单事件 Pro 工具失败不影响其他事件；
- 纯价格事件 not_applicable；
- 不同事件 messages 不串上下文；
- 相同公司工具证据缓存复用。

完成后运行 tests/test_daily_radar.py、相关新测试、全量 pytest、Ruff 和 git diff --check。

完成后停止，不进入阶段 5，不 commit、不 push。汇报新链路、原 Top 5 行为如何替换、实际 Pro 选择规则、
失败隔离、测试结果和未实现内容。
建议 commit message：feat: route full daily news analysis by impact
```

## 8. 阶段 5：Snapshot v2.2 与 Markdown 报告

### 8.1 范围

升级后端输出，不改前端：

- `schema_version = "2.2"`
- event importance、tier、reason codes
- candidate positive/negative magnitude、confidence、conflict、priority、breakdown
- summary critical/high/verify-first 计数和 scoring version
- Markdown 重大事件、重点股票、高影响待核验、Watchlist 风险区

### 8.2 验收

- v2.2 严格校验所有新增枚举和 `0..100` 数值；
- Snapshot 不把影响分描述为收益预测；
- 全量事件至少存在于目录并带 route 状态；
- 原子写失败不覆盖上一份成功 Snapshot；
- 同股跨事件不被简单平均；
- Pro、Flash、deterministic 清晰区分。

### 8.3 可复制提示词

```text
请实施“全量新闻事件评分”的阶段 5：DailyRadarSnapshot v2.2 与 Markdown 报告。

工作目录：
/Users/nickcandy/Desktop/workspace/finance-research-lab

开始前必须阅读：
1. docs/full-news-impact-scoring-design.md 第 10、11、14、15、17 节
2. 阶段 4 的内部运行结果合同
3. src/finance_research_lab/daily_radar_snapshot.py
4. src/finance_research_lab/daily_radar_report.py
5. src/finance_research_lab/event_catalog.py
6. tests/test_daily_radar_snapshot.py
7. tests/test_daily_radar.py

目标：
- 将 Snapshot 从 2.1 升级到 2.2。
- 增加设计文档列出的 events、candidate_groups 和 summary 字段。
- feature_breakdown 必须保留特征分、reason codes 和证据引用。
- Markdown 增加重大事件榜、重点股票榜、高影响待核验和 Watchlist 风险预警。
- 清楚标识 Pro / Flash / deterministic / not_applicable。
- 同股跨事件按 max positive、max negative、置信度和独立印证排序，不做简单平均。

约束：
- 先写/修改严格合同测试。
- 后端和 JSON 合同一次升级，不保留未被调用方需要的兼容字段。
- 继续原子写 Snapshot；校验失败不得覆盖上一份成功文件。
- 所有 0..100 字段拒绝 bool、越界和错误类型。
- priority_level、analysis_tier、scoring_version 必须存在。
- 页面尚未升级，本阶段不要修改 web/。
- 不改评分公式或路由规则。

完成后运行 Snapshot、日报、Web API 相关测试，再运行全量 pytest、Ruff 和 git diff --check。

完成后停止，不进入阶段 6，不 commit、不 push。请附一份最小 v2.2 JSON 字段摘要和迁移影响。
建议 commit message：feat: expose impact scoring in radar snapshot
```

## 9. 阶段 6：前端 v2.2 展示

### 9.1 页面最小范围

1. 重大事件榜；
2. 重点股票榜；
3. 高影响待核验；
4. Watchlist 风险预警；
5. 分数 breakdown；
6. 支持/反对证据；
7. 分析层级标签。

不在本阶段增加交易建议、收益概率、目标价、仓位或实时行情功能。

### 9.2 验收

- TypeScript 严格类型与 v2.2 对齐；
- Loading / Success / Error 三态明确；
- `verify_first` 不伪装成高置信候选；
- 正负影响同时可见；
- 用户能看到分数由哪些 feature 和证据构成；
- 移动端可读；
- 组件超过 150 行时按职责拆分。

### 9.3 可复制提示词

```text
请实施“全量新闻事件评分”的阶段 6：前端 DailyRadarSnapshot v2.2 展示。

工作目录：
/Users/nickcandy/Desktop/workspace/finance-research-lab

开始前必须阅读：
1. docs/full-news-impact-scoring-design.md 第 11、14 节
2. 阶段 5 的 v2.2 JSON 合同和测试 fixture
3. web/src/types/radar.ts
4. web/src/App.tsx
5. web/src/components/
6. web 现有测试与 package.json scripts

目标：
- 将前端类型严格升级到 Snapshot 2.2，禁止 any。
- 展示重大事件榜、重点股票榜、高影响待核验、Watchlist 风险预警。
- 展示 positive_magnitude、negative_magnitude、confidence、conflict_score、
  priority_level、analysis_tier、feature_breakdown 和 reason_codes。
- 支持证据和反对证据分开展示。
- 明确显示“影响分是研究优先级，不是收益预测”。

约束：
- 只用现有 React + TypeScript + Tailwind 风格。
- API 交互必须有 Loading / Success / Error 三态。
- 不增加交易建议、目标价、收益概率或仓位。
- verify_first 必须使用明显的“待核验”状态。
- 正负影响不能合成一个净分隐藏。
- 单组件超过 150 行按职责拆分。
- 不修改后端评分、路由或 Snapshot 合同。
- 不编辑 web/dist 生成物，除非仓库现有发布流程明确要求且用户当次授权。

至少覆盖：
- critical/high/verify_first/medium/low；
- Pro/Flash/deterministic/not_applicable；
- 正负影响并存；
- breakdown 展开；
- 空列表；
- Snapshot 加载失败；
- v2.1 输入被明确拒绝或显示版本错误。

运行前端测试、类型检查和构建；再运行后端全量 pytest、Ruff 和 git diff --check。

完成后停止，不进入阶段 7，不 commit、不 push。汇报页面变化、类型变化、三态处理和验证结果。
建议 commit message：feat: render ranked news impact signals
```

## 10. 阶段 7：Point-in-time、回放与全链路验收

### 10.1 范围

保存每日生成时真实可见的输入、分数和版本，提供固定 fixture 回放。第一版不做自动调权，也不把未来收益写回当日信号。

### 10.2 验收

- 原始 event catalog、Claim、assessment 和 Snapshot 可以按 run ID 对齐；
- 历史信号不会被后续新闻或财务数据覆盖；
- 相同输入、缓存和 `scoring_version` 输出完全一致；
- 新评分版本不会改写旧版本文件；
- 固定回放覆盖全量、部分 Pro、全部 fallback 和工具失败；
- 输出可用于后续 walk-forward，但当前不声称预测收益。

### 10.3 可复制提示词

```text
请实施“全量新闻事件评分”的阶段 7：Point-in-time 保存、确定性回放与全链路验收。

工作目录：
/Users/nickcandy/Desktop/workspace/finance-research-lab

开始前必须阅读：
1. docs/full-news-impact-scoring-design.md 第 15、17、19 节
2. docs/cost-aware-evidence-pipeline-plan.md 第 10、12 节
3. 阶段 1～6 的公开合同和测试
4. src/finance_research_lab/event_catalog.py
5. src/finance_research_lab/event_analysis.py
6. src/finance_research_lab/daily_radar_snapshot.py

目标：
- 按 run_id 保存 news_item_ids、claim_ids、event_id、symbol、三套分数、方向、冲突、
  priority_level、feature_breakdown、reason_codes、scoring_version 和 generated_at。
- 使用原子写和不可变版本路径，禁止新运行覆盖旧 run 的原始信号。
- 增加固定 event catalog、Claim cache、公司/财务/行情 cache 的回放入口或测试 helper。
- 增加端到端 fixture，证明相同输入和 scoring_version 输出确定。
- 为后续结果标签预留独立文件/合同，但不在本阶段自动抓未来收益或调权。

约束：
- 先写失败测试。
- point-in-time 文件只追加新 run/version，不原地修改旧信号。
- 评分失败和工具失败也必须留下状态与 warning。
- 不使用未来新闻或事后修正数据补写历史特征。
- 不自动校准权重。
- 不增加收益概率字段。
- 不做无关存储抽象；优先沿用现有 reports/event-catalogs/event-analyses 目录风格。

端到端场景至少覆盖：
1. 全量输入均生成 Claim 或 fallback；
2. 只有规则选出的事件进入 Pro；
3. critical/high/verify_first 排序正确；
4. 同源转载不加分；
5. 正负证据不净额；
6. Pro 单事件失败隔离；
7. Snapshot 2.2 严格校验；
8. 第二次相同输入主要命中缓存；
9. 固定输入回放字节级或结构级一致。

完成后运行：
.venv/bin/pytest -q
.venv/bin/ruff check src tests
前端测试、类型检查和构建
git diff --check
git status --short

完成后停止，不 commit、不 push。请给出：
1. 完成定义逐项对照；
2. 全部验证结果；
3. 剩余风险；
4. 实际运行一次 daily-radar 的安全命令；
5. 建议 commit message：feat: persist point in time impact signals
```

## 11. 每阶段上下文控制

编码 Agent 不需要携带前一阶段的完整聊天记录。每次新会话只提供：

```text
稳定上下文：
- 本实施计划
- 两份设计文档
- 当前阶段涉及的源文件和测试
- git status / git diff

动态上下文：
- 本阶段目标
- 上一阶段已经落库的公开合同
- 当前失败测试

不要携带：
- 前几阶段完整对话
- 与当前阶段无关的大段源码
- 其他事件的运行时 messages
- 已经由代码常量表达的评分规则全文
```

运行时新闻分析同样隔离上下文：

```text
Flash：一个批次的 NewsItem JSON，不带历史对话，不带工具。
Pro：一个 MarketEvent 的 Claim + ledger + 当前工具结果，不带其他事件对话。
代码：评分常量、路由阈值和 schema，不放进自然语言历史。
缓存：通过稳定 ID/content_hash 查询，不通过聊天历史记忆。
```

工具上下文由模型 API 原生协议管理：

```text
request.messages = system + current event user payload + current event tool history
request.tools    = 当前阶段允许的工具白名单

assistant 返回 tool_calls
→ 执行工具
→ 追加 role=tool、tool_call_id 和结构化 ToolResult
→ 再次请求模型
```

工具定义不要伪装成普通 user 消息；不同事件不能共享 tool call 历史。

## 12. 推荐执行方式

最稳妥的执行节奏：

```text
阶段 1 → 测试 → review → commit
阶段 2 → 测试 → review → commit
...
阶段 7 → 全量验收 → review → commit
```

阶段 1～3 完成后，评分和全量抽取能力已经存在，但生产日报行为不变。阶段 4 是真正切换全量链路的开关，
风险最高，应单独评审。阶段 5～7 负责把结果稳定地交付给用户并形成后续校准基础。
