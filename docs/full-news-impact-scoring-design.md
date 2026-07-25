# 全量新闻事件分级与股票影响评分设计

## 文档状态

- 状态：V2.3 已实施
- 当前版本：V2.3
- 适用入口：`daily-radar`、单事件按需分析
- 关联文档：
  - [`cost-aware-evidence-pipeline-plan.md`](cost-aware-evidence-pipeline-plan.md)：全量 Claim、证据账本、Flash/Pro 成本与路由
  - [`impact-alert-research-plan.md`](impact-alert-research-plan.md)：现有 V2.1 方向、影响指数、Watchlist 预警
- 产品边界：研究辅助，不预测收益，不输出买卖、目标价或仓位

## 1. 背景与问题

当前 `daily-radar` 已经抓取最近 24 小时的全部同花顺新闻，完成确定性去重、事件聚类并保存完整
event catalog，但只有排名前 5 的可研究事件进入 `_analyze_market_event()`。

现有排序和影响指数存在三个限制：

1. `rank_hot_events()` 只按独立来源数量和发布时间排序，不能识别“传播不广但对某家公司影响很大”的事件。
2. `stock_impact_score()` 只根据 `high / medium / low` 和 `direct / indirect / sentiment` 计算固定分数，
   没有使用订单占营收、业务暴露度、产能影响、政策落地程度等可验证事实。
3. 事件和股票的方向、影响幅度、证据可信度被压缩到少数字段，无法正确表达“高影响低可信”和
   “正负证据同时很强”。

目标流程必须从：

```text
先选 Top 5
→ 再理解新闻
```

调整为：

```text
全量有效新闻
→ 全量提取 Claim
→ 按事件和股票聚合证据
→ 计算重要性、影响幅度和置信度
→ 分级
→ 只对重要事件做 Pro 深度分析
```

## 2. 目标

### 2.1 功能目标

- 所有有效、去重后的新闻和公告必须生成 Claim，或明确记录 deterministic fallback。
- 每个事件得到可解释的事件重要性和重要级别。
- 每个“事件—股票”关系得到方向、正负影响幅度、置信度和优先级。
- 同一股票跨事件聚合时保留全部支持、反对和风险证据。
- Pro 深度分析由确定性规则选择，不由 LLM 直接决定。
- 所有分数保存 feature breakdown 和 reason codes，可回放、可测试、可调整版本。

### 2.2 非目标

- 不把影响分解释为预期收益率。
- 不根据分数输出买入、卖出或仓位建议。
- 不让 LLM 直接生成最终数值分数。
- 不把同源转载当成多份独立证据。
- 不在没有 point-in-time 数据和样本外验证前输出收益概率。
- 第一版不引入机器学习排序模型、向量数据库或知识图谱数据库。

## 3. 设计原则

### 3.1 三个维度必须分开

系统分别计算：

```text
事件重要性 event_importance
股票影响幅度 stock_impact_magnitude
证据置信度 confidence
```

三者回答不同问题：

| 维度 | 回答的问题 |
| --- | --- |
| 事件重要性 | 这件事本身有多大、影响面有多广、是否改变已有预期 |
| 股票影响幅度 | 这件事对某家公司的经营或风险暴露可能有多大 |
| 证据置信度 | 这个事实和公司映射有多可靠 |

`magnitude=90, confidence=20` 应进入“高影响待核验”；`magnitude=50, confidence=90` 应进入
“中等影响、高可信”。两者不能压缩成同一个总分。

### 3.2 先提取事实，再计算分数

LLM/Flash 只负责将新闻压缩为结构化 Claim 和候选特征。Tools 补齐公司身份、主营、财务、公告和行情事实。
最终分数由代码根据固定权重计算。

### 3.3 缺数据时降低上限

不能把缺失字段自动解释为中性或零影响。缺乏关键量化证据时：

- 保留 `unknown` 和缺失原因；
- 限制相应维度的最高分；
- 降低置信度；
- 必要时进入 `verify_first`，而不是进入正式重点候选。

### 3.4 正负证据不做简单净额

同一股票同时出现 `positive=80` 和 `negative=70` 时，不输出 `+10`。系统必须保留两侧：

```text
positive_magnitude = 80
negative_magnitude = 70
direction = mixed
conflict_score = 70
```

### 3.5 权重必须版本化

每次运行保存 `scoring_version`。调整权重时增加版本，不用新规则重写历史结果，确保 point-in-time
回测可以复现当时的真实决策。

## 4. 总体流程

```text
EventSource.fetch()
→ NewsItem 标准化
→ content_hash / origin_key 去重
→ cluster_market_events()
→ ClaimPipeline.extract()
→ 本地 A 股 universe 校验
→ EvidenceLedgerBuilder
→ EventImportanceScorer
→ StockImpactScorer
→ PriorityClassifier
→ AnalysisRouter
→ Pro / Flash / deterministic 输出
→ DailyRadarSnapshot v2.2
```

分工边界：

```text
LLM       提取事件、数字、方向、公司候选和原文证据
Tools     校验公司身份、主营、公告、财报、行情和产业链关系
代码      去重、特征计算、评分、分级、路由和最终验证状态
```

## 5. 数据合同

### 5.1 Claim 扩展

沿用成本方案中的 `Claim`，增加评分需要的量化字段：

```python
@dataclass(frozen=True)
class QuantitativeFact:
    metric: str
    value: float
    unit: str
    period: str
    source_item_id: str


@dataclass(frozen=True)
class Claim:
    id: str
    event_id: str
    source_item_ids: tuple[str, ...]
    subject: str
    predicate: str
    object: str
    claim_type: Literal[
        "fact",
        "forecast",
        "opinion",
        "risk",
        "denial",
        "market_reaction",
    ]
    event_type: str
    direction: ImpactDirection
    time_horizon: Literal["immediate", "short", "medium", "long", "unknown"]
    affected_symbols: tuple[str, ...]
    quantitative_facts: tuple[QuantitativeFact, ...]
    confidence: ConfidenceLevel
    occurred_at: str
```

规则：

- `quantitative_facts` 必须来自原文，不允许 LLM 补造缺失数字。
- 每个数字必须能回溯到 `source_item_id`。
- 媒体判断使用 `opinion`，不能伪装为 `fact`。
- 框架协议、预测和正式落地事件必须使用不同 `claim_type` 或事件状态。

### 5.2 评分特征

```python
@dataclass(frozen=True)
class FeatureScore:
    value: int
    reason_codes: tuple[str, ...]
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class EventImportanceFeatures:
    materiality: FeatureScore
    breadth: FeatureScore
    novelty: FeatureScore
    immediacy: FeatureScore


@dataclass(frozen=True)
class StockImpactFeatures:
    directness: FeatureScore
    exposure: FeatureScore
    economic_scale: FeatureScore
    duration: FeatureScore
    sensitivity: FeatureScore


@dataclass(frozen=True)
class ConfidenceFeatures:
    source_quality: FeatureScore
    corroboration: FeatureScore
    identity_verification: FeatureScore
    quantitative_completeness: FeatureScore
    consistency: FeatureScore
```

`FeatureScore.value` 范围为 `0..100`，并使用 `reason_codes` 和 `evidence_refs` 将分数与解释信息强绑定。
禁止只保存一个无法解释的总分。

### 5.3 最终评估

```python
@dataclass(frozen=True)
class ImpactAssessment:
    event_id: str
    symbol: str
    direction: ImpactDirection
    event_importance: int
    positive_magnitude: int
    negative_magnitude: int
    confidence: int
    conflict_score: int
    event_features: EventImportanceFeatures
    positive_features: StockImpactFeatures | None
    negative_features: StockImpactFeatures | None
    confidence_features: ConfidenceFeatures
    priority_level: Literal[
        "critical",
        "high",
        "medium",
        "low",
        "verify_first",
    ]
    analysis_tier: Literal[
        "pro",
        "flash",
        "deterministic",
        "not_applicable",
    ]
    reason_codes: tuple[str, ...]
    scoring_version: str
```

`symbol` 可以为空，用于尚未映射到具体公司的宏观或行业事件。没有经过本地 universe 校验的股票关系不能进入
正式重点股票榜。

## 6. 事件重要性评分

### 6.1 公式

```python
event_importance = round_half_up(
    materiality * 0.35
    + breadth * 0.25
    + novelty * 0.20
    + immediacy * 0.20
)
```

所有加权分统一使用常规四舍五入 `ROUND_HALF_UP`，不使用 Python 内置 `round()` 的银行家舍入。
由于输入和权重都是非负整数，实现可使用 `(weighted_sum + 50) // 100`，避免浮点误差。

| 特征 | 权重 | 含义 |
| --- | ---: | --- |
| `materiality` | 35% | 金额、利润、产能、政策范围等经济实质 |
| `breadth` | 25% | 影响单公司、产业链、行业还是全市场 |
| `novelty` | 20% | 新事实、旧闻更新还是重复转载 |
| `immediacy` | 20% | 已生效、即将生效还是长期规划 |

来源质量不放入事件重要性。重大传闻仍可能是高重要性，但必须表现为低置信度和 `verify_first`。

### 6.2 `materiality`

优先使用相对指标，不用绝对金额直接比较不同公司：

```text
合同金额 / TTM 营收
利润影响 / TTM 净利润
投资金额 / 总资产
减持或回购金额 / 市值
受影响产能 / 总产能
相关业务收入 / 总收入
```

缺少事件类型对应的核心相对指标时：

```python
materiality = min(materiality, 60)
```

### 6.3 `breadth`

第一版固定区间：

| 范围 | 建议分值 |
| --- | ---: |
| 单个非核心产品或局部事项 | 15～30 |
| 单家公司核心业务 | 40～60 |
| 产业链单一环节或细分行业 | 60～75 |
| 多个产业链环节或大行业 | 75～90 |
| 全市场、宏观制度或系统性风险 | 90～100 |

传播媒体数量不直接增加 `breadth`。

### 6.4 `novelty`

| 情况 | 建议分值 |
| --- | ---: |
| 完全重复转载 | 0 |
| 旧事件无新增事实 | 10～20 |
| 旧事件增加执行进度或数字 | 40～60 |
| 新事件，但符合既有预期 | 60～75 |
| 改变已有判断或明显超预期 | 80～100 |

`novelty` 需要与历史 event catalog 或同一运行内更早的 Claim 比较。第一版如果没有历史索引，只比较本次运行和
本地缓存，并将长期新颖度标为待验证。

### 6.5 `immediacy`

| 状态 | 建议分值 |
| --- | ---: |
| 无明确时间表 | 20 |
| 一年以上远期规划 | 30～40 |
| 未来一至四个季度 | 50～70 |
| 已签约、已获批、即将执行 | 75～90 |
| 已生效、已停产、已处罚、已披露实际结果 | 90～100 |

## 7. 股票影响幅度评分

### 7.1 公式

```python
stock_impact_magnitude = round_half_up(
    directness * 0.25
    + exposure * 0.25
    + economic_scale * 0.25
    + duration * 0.15
    + sensitivity * 0.10
)
```

实际实现同样使用 `ROUND_HALF_UP`。

| 特征 | 权重 | 含义 |
| --- | ---: | --- |
| `directness` | 25% | 公司与事件之间的关系有多直接 |
| `exposure` | 25% | 相关业务占公司经营的比例 |
| `economic_scale` | 25% | 事件相对营收、利润、资产、产能或市值的量级 |
| `duration` | 15% | 一次性、短期还是长期影响 |
| `sensitivity` | 10% | 产能、技术、认证、客户和替代壁垒 |

### 7.2 `directness`

第一版固定映射：

| 关系 | 分值 |
| --- | ---: |
| 公司正式公告直接涉及 | 100 |
| 政府、监管或交易所文件明确点名 | 95 |
| 可靠媒体原文明确点名公司 | 85 |
| 公司主营产品与事件位于同一产业链节点 | 70 |
| 一跳上游或下游 | 45 |
| 两跳产业链关系 | 25 |
| 只有行业或主题概念重合 | 10 |
| 纯市场情绪映射 | 5 |
| 无可验证关系 | 0 |

同环节和上下游距离由现有 `value_chains.py` 确定。行业一致不能单独证明直接关系。

### 7.3 `exposure`

优先读取：

```text
相关产品收入占比
相关业务毛利占比
相关客户收入占比
相关产能占比
主营描述和产品节点
```

第一版区间：

| 业务暴露 | 建议分值 |
| --- | ---: |
| 仅概念相关，无产品证据 | 0～20 |
| 有产品关系但收入未知 | 30～45 |
| 相关业务占收入 10%～30% | 45～60 |
| 相关业务占收入 30%～60% | 60～80 |
| 核心或高度纯粹标的 | 80～100 |

只有行业字段、没有主营或产品证据时：

```python
exposure = min(exposure, 30)
```

### 7.4 `economic_scale`

不同事件类型使用不同归一化指标，详见第 9 节。缺乏公司基准数据时，不允许由 LLM自行估算：

```python
economic_scale = min(rule_based_estimate, 50)
```

### 7.5 `duration`

| 影响周期 | 建议分值 |
| --- | ---: |
| 单日情绪或临时波动 | 10～20 |
| 数日到一个月 | 25～40 |
| 一个季度 | 40～55 |
| 半年至一年 | 55～75 |
| 多年合同、产能或制度变化 | 75～90 |
| 长期结构性壁垒变化 | 90～100 |

`duration` 继续只参与现有影响幅度计算，权重保持 15%。从 Snapshot v2.3 开始，系统另外输出
可解释的影响周期，不用一个分数代替时间判断：

```text
positive_horizon / negative_horizon
  market       # 市场反应周期，单位为交易日
  fundamental  # 基本面兑现周期，单位为自然月
```

每层周期包含分类、最小/最大持续时间、置信度、判断依据、Claim 引用和失效条件。分类为
`immediate / short / medium / long / structural / unknown`。明确合同期限、政策有效期、交付期、
建设期或量产期优先；其次使用 Claim 周期；再其次使用事件类型默认值。证据不足时必须输出
`unknown`，禁止推算具体结束日期。正向和负向周期独立保存，跨事件聚合时分别跟随正向或负向
影响幅度最高的 assessment。

### 7.6 `sensitivity`

综合考虑：

- 公司是否为唯一或少数供应商；
- 客户认证周期和切换成本；
- 产能是否紧缺；
- 产品是否容易替代；
- 公司能否将成本变化传导给下游；
- 事件影响的是收入端、成本端还是核心经营资质。

第一版使用本地产业链配置和固定 reason codes，不让 LLM自由打分。

## 8. 证据置信度评分

### 8.1 公式

```python
confidence = round_half_up(
    source_quality * 0.35
    + corroboration * 0.20
    + identity_verification * 0.20
    + quantitative_completeness * 0.15
    + consistency * 0.10
)
```

实际实现同样使用 `ROUND_HALF_UP`。

| 特征 | 权重 |
| --- | ---: |
| 来源质量 | 35% |
| 独立来源印证 | 20% |
| 公司身份和关系校验 | 20% |
| 量化数据完整度 | 15% |
| 证据一致性 | 10% |

### 8.2 来源质量

第一版固定区间：

| 来源 | 建议分值 |
| --- | ---: |
| 交易所、监管、政府正式文件 | 100 |
| 公司正式公告 | 95 |
| 公司新闻稿或官方发布 | 80 |
| 可靠媒体引用原文 | 70 |
| 可靠媒体独家报道 | 60 |
| 二手媒体转述 | 45 |
| 无明确来源 | 20 |
| 传闻或无法验证来源 | 10 |

来源质量只表示事实来源可靠性，不表示事件方向一定正确。公司正式预测仍需要根据预测性质降低
`quantitative_completeness` 或 `consistency`。

### 8.3 独立来源印证

按 `origin_key` 和 `content_hash` 分组：

- 相同 `content_hash`：完全重复，只计一次；
- 相同 `origin_key`：同源转述，只增加传播度；
- 不同高质量原始来源描述同一事实：增加印证；
- 同一来源的多篇更新：只保留最新事实，不重复加分。

同一方向的多来源不累加影响幅度，只增加置信度。第一版最多认可三个独立来源，避免媒体数量主导排序。

### 8.4 公司身份和关系校验

| 校验结果 | 建议分值 |
| --- | ---: |
| 证券代码、公司名和公告主体全部一致 | 100 |
| 公司被原文点名且本地 universe 唯一匹配 | 90 |
| 同一产品节点，主营证据完整 | 75 |
| 一跳产业链，本地关系明确 | 55 |
| 仅 LLM 提出、无本地产品关系 | 20 |
| 身份冲突或无法解析 | 0 |

### 8.5 一致性和冲突

`consistency` 不是简单计算正负数量。系统必须区分：

- 不同时间跨度，不视为冲突；
- 事实与观点，不直接互斥；
- 同一主体、指标、时间和口径下的互斥描述，才增加冲突；
- 官方澄清或否认应明确关联被否认的 Claim。

高冲突不代表事件不重要。它会降低置信度，同时提高研究优先级。

## 9. 事件类型量化规则

### 9.1 订单和合同

特征：

```text
合同金额 / TTM 营收
合同金额 / 市值
最低采购承诺
履约周期
正式合同 / 中标通知 / 框架协议 / 意向协议
```

规则示例：

| 合同金额 / TTM 营收 | `economic_scale` 基础分 |
| --- | ---: |
| < 2% | 15 |
| 2%～10% | 35 |
| 10%～30% | 60 |
| 30%～50% | 80 |
| > 50% | 95 |

框架协议、意向协议或金额上限不确定时，对 `immediacy` 和 `confidence` 降级。

### 9.2 业绩、指引和财务结果

特征：

```text
实际值相对去年同期
实际值相对预告区间中点
是否扭亏
主营利润 / 一次性损益
现金流与利润是否一致
```

没有一致预期数据时，不使用“超预期”作为事实。媒体使用“超预期”只能保存为 `opinion`，除非提供可验证基准。

### 9.3 回购、减持、增发和控制权变化

特征：

```text
金额 / 市值
股份数量 / 总股本
行为人持股变化比例
是否改变控制权
计划 / 已实施
```

控制权变化属于硬升级条件，不只依赖数值分。

### 9.4 诉讼、处罚、停产和风险事件

特征：

```text
涉案金额 / 净资产
涉案金额 / TTM 净利润
受影响产能 / 总产能
是否影响核心资质
是否存在停产、退市或重大偿付风险
```

核心资质被暂停、主要工厂停产或重大退市风险属于硬升级条件。

### 9.5 扩产和资本开支

特征：

```text
投资金额 / 总资产
新增产能 / 现有产能
资金来源
客户或订单锁定程度
预计投产时间
```

只有规划、没有资金和时间表时，`immediacy` 不能高于 40。

### 9.6 商品价格和成本变化

特征：

```text
相关产品收入占比
原材料成本占比
价格变化幅度
公司能否向下游转嫁
库存周期
```

同一价格上涨对上游生产商和下游使用者方向可能相反，必须分别生成股票影响关系。

第一版按价格绝对变化幅度使用固定分档：

| 价格绝对变化幅度 | `economic_scale` 基础分 |
| --- | ---: |
| < 2% | 15 |
| 2%～5% | 35 |
| 5%～10% | 60 |
| 10%～20% | 80 |
| >= 20% | 95 |

### 9.7 政策和监管

特征：

```text
征求意见 / 会议表态 / 正式发布 / 已生效
覆盖行业范围
执行时间
金额、配额、准入或标准变化
公司业务暴露比例
```

政策正式发布提高来源质量和 `immediacy`，但股票影响仍必须经过业务暴露和产业链关系校验。

### 9.8 产品获批、研发和临床结果

特征：

```text
研发阶段
是否正式获批
目标市场
商业化时间
相关业务在公司估值和收入中的占比
失败或替代风险
```

早期研发和媒体预测不得使用与正式获批相同的基准分。

## 10. 多条证据合并

### 10.1 同方向证据

同一“事件—股票—方向”关系：

```python
combined_magnitude = strongest_independent_claim

if second_high_quality_independent_source:
    combined_magnitude += 5

if third_high_quality_independent_source:
    combined_magnitude += 5

combined_magnitude = min(combined_magnitude, 100)
```

重复转载不增加影响幅度。第二、第三个独立来源主要增加置信度，幅度补偿最多 10 分。

### 10.2 正负证据

分别计算：

```text
positive_magnitude
negative_magnitude
```

方向规则：

```python
if positive_magnitude >= negative_magnitude + 20:
    direction = "positive"
elif negative_magnitude >= positive_magnitude + 20:
    direction = "negative"
elif max(positive_magnitude, negative_magnitude) == 0:
    direction = "unknown"
else:
    direction = "mixed"
```

冲突分第一版取：

```python
conflict_score = min(positive_magnitude, negative_magnitude)
```

只有满足第 8.5 节的同口径互斥条件时，才将证据记入强冲突。

### 10.3 同一股票跨事件聚合

不能平均所有事件，也不能把正负简单相减。

每日股票摘要保留：

```text
max_positive_magnitude
max_negative_magnitude
event_count
independent_source_count
conflict_score
latest_event_at
```

排序使用最大影响侧、置信度和跨事件印证，不让大量低分事件稀释一个重大事件。

## 11. 重要级别与深度分析路由

### 11.1 `critical`

满足任一条件：

- 股票影响幅度 `>= 75` 且置信度 `>= 60`；
- 官方重大公告且股票影响幅度 `>= 60`；
- Watchlist 负面影响 `>= 60`；
- 正面和负面影响都 `>= 60`；
- 控制权、核心资质、重大停产、重大诉讼或退市风险；
- 同一股票被多个独立重大事件影响。

处理：进入 Pro 深度分析，并在重点事件或重点股票区域展示。

### 11.2 `verify_first`

条件：

```text
max(positive_magnitude, negative_magnitude) >= 65
confidence < 50
```

处理：优先调用公告、财报或原始政策工具核验。核验前不能作为正式高置信候选展示。

### 11.3 `high`

满足任一条件：

- 股票影响幅度 `60..74` 且置信度 `>= 50`；
- 事件重要性 `>= 75`，并存在至少一个已验证 A 股关系；
- 多个高质量独立来源对核心事实同向印证。

处理：进入 Pro；如果 Pro 处理失败，则降级输出 Flash 简报并保留 warning。

### 11.4 `medium`

条件：

- 股票影响幅度 `35..59`；
- 产业链映射成立但不是直接影响；
- 事件有实际内容，但经济量级有限或数据不完整。

处理：输出 Flash 简报，不默认执行完整证据工具链。

### 11.5 `low`

条件：

- 股票影响幅度 `< 35`；
- 只有行业或主题概念重合；
- 重复转载；
- 普通行情播报；
- 无法验证公司或产业链关系。

处理：进入完整事件目录；纯行情等内容标记为 `not_applicable`，其余生成 deterministic 摘要。

## 12. LLM、Tools 和代码的职责

### 12.1 LLM/Flash

允许输出：

- Claim；
- 事件类型；
- 主体、行为、对象；
- 原文中的金额、比例、时间和单位；
- 方向假设；
- 公司名称和代码候选；
- 引用的 `source_item_id`。

禁止输出：

- 最终事件重要性；
- 最终股票影响分；
- 最终置信度；
- 未出现在原文或工具结果中的财务数字；
- 收益概率、目标价和仓位。

### 12.2 Tools

负责：

- 公司名和证券代码校验；
- 主营、产品和产业链节点；
- 公告原文；
- 财务基准；
- 行情和成交量；
- 事件涉及金额相对公司规模的分母。

### 12.3 代码

负责：

- 来源身份和重复检测；
- 特征计算；
- 缺失上限；
- 分数计算；
- 正负证据合并；
- 冲突检测；
- 重要级别；
- Pro/Flash/deterministic 路由；
- `verified / unverified / excluded` 最终状态。

## 13. Fallback

### 13.1 Claim 提取失败

- 单批失败重试一次；
- 再失败则使用标题、显式公司名、方向词、金额和事件类型规则提取；
- 标记 `analysis_tier=deterministic`；
- `confidence` 上限为 35；
- 不允许该批次静默消失。

### 13.2 公司或财务证据缺失

- 保留事件和 Claim；
- 对 `exposure`、`economic_scale` 和 `confidence` 设置上限；
- 股票状态保持 `unverified`；
- 高潜在影响进入 `verify_first`。

### 13.3 来源冲突

- 保留两侧证据；
- 增加 `conflict_score`；
- 降低 `consistency`；
- 高影响冲突事件升级到 Pro，而不是被过滤。

### 13.4 Pro 或工具失败

- 保留 Flash/规则结果；
- 不覆盖上一份成功深度分析；
- 在 Snapshot 和报告中显示 warning；
- 不将降级结果伪装成 Pro 结果。

## 14. Snapshot 与页面

`DailyRadarSnapshot v2.2` 增加：

```text
events[].event_importance
events[].importance_level
events[].confidence
events[].analysis_tier
events[].reason_codes[]

candidate_groups[].positive_magnitude
candidate_groups[].negative_magnitude
candidate_groups[].confidence
candidate_groups[].conflict_score
candidate_groups[].priority_level
candidate_groups[].feature_breakdown
candidate_groups[].reason_codes[]

summary.critical_event_count
summary.high_event_count
summary.verify_first_count
summary.scoring_version
```

页面至少显示：

1. 重大事件榜；
2. 重点股票榜；
3. 高影响待核验；
4. Watchlist 风险预警；
5. 每个分数的 feature breakdown；
6. 支持证据、反对证据和来源；
7. `Pro / Flash / deterministic` 分析层级。

“影响分”统一描述为研究优先级，不显示为收益预测。

## 15. Point-in-time 记录与校准

### 15.1 必须保存的信号

每天保存生成时真实可见的：

```text
news_item_ids
claim_ids
event_id
symbol
event_importance
positive_magnitude
negative_magnitude
direction
confidence
priority_level
feature_breakdown
reason_codes
scoring_version
generated_at
```

禁止事后用新增新闻或修正后的财务数据覆盖历史输入。

### 15.2 结果标签

后续记录：

```text
开盘到收盘
1 个交易日
5 个交易日
20 个交易日
相对宽基指数的异常收益
相对行业指数的异常收益
异常成交量
异常波动率
```

影响分初期只用于排序。只有完成 point-in-time 记录和 walk-forward 样本外验证后，才可以讨论是否增加概率字段。

### 15.3 校准指标

- 重点股票 Top K 对异常波动公司的覆盖率；
- `critical / high` 的 Precision@K；
- 影响幅度和绝对异常收益的排序相关性；
- 正负方向命中率；
- 高置信组是否明显优于低置信组；
- 不同事件类型的有效性；
- `verify_first` 最终被证实或否定的比例。

采用：

```text
历史窗口调整权重
→ 固定 scoring_version
→ 下一时间窗口验证
→ 再发布新版本
```

不能使用当天结果反向修改当天分数。

## 16. 示例

### 16.1 正式重大订单

输入：

```text
公司正式公告获得 20 亿元订单
TTM 营收 25 亿元
合同分三年执行
涉及公司核心产品
```

示例评分：

```text
事件重要性
materiality=90
breadth=50
novelty=90
immediacy=80
event_importance=78

股票影响
directness=100
exposure=90
economic_scale=95
duration=75
sensitivity=60
magnitude=89

置信度
source_quality=95
corroboration=80
identity_verification=100
quantitative_completeness=90
consistency=90
confidence=92
```

结果：

```text
priority_level=critical
analysis_tier=pro
direction=positive
```

### 16.2 二手行业乐观报道

输入：

```text
二手媒体称 AI 需求旺盛，可能利好光模块
没有公司公告
没有订单或收入数字
只通过一跳产业链关联公司
```

结果示例：

```text
event_importance=45
positive_magnitude=38
confidence=35
priority_level=medium
analysis_tier=flash
```

不能因为出现“AI”“需求旺盛”“利好”就进入正式重点股票榜。

### 16.3 高影响传闻

输入：

```text
无明确来源称某公司将获得重大订单
潜在订单金额相对公司营收很高
公司和交易所尚未确认
```

结果示例：

```text
positive_magnitude=80
confidence=20
priority_level=verify_first
```

系统应优先查公告和原始来源，不作为高置信利好展示。

## 17. 测试

### 17.1 纯计算单元测试

- 每个评分特征的边界值；
- 缺数据上限；
- 权重固定和整数舍入；
- `scoring_version`；
- 正负方向和 mixed；
- 同源转载不加分；
- 独立来源最多增加固定补偿；
- 高影响低可信进入 `verify_first`；
- 重大负面 Watchlist 进入 `critical`。

### 17.2 事件类型测试

- 合同金额占营收不同比例；
- 框架协议与正式合同；
- 业绩增长但主要来自一次性损益；
- 回购、减持和控制权变化；
- 诉讼金额相对净资产和利润；
- 产能扩张有无资金和时间表；
- 商品涨价对上下游方向相反；
- 征求意见与正式生效政策；
- 研发预测与正式获批。

### 17.3 集成测试

- 全量 Claim 到事件和股票评分；
- 单批 Claim fallback 不丢新闻；
- 公司证据缺失时正确降级；
- 高冲突事件进入 Pro；
- 同股跨事件不被简单平均；
- Snapshot 保存 breakdown 和 reason codes；
- 相同输入、相同评分版本得到相同输出。

### 17.4 回放测试

使用固定 event catalog：

- 冻结输入时间；
- 冻结公司和财务缓存；
- 冻结评分配置；
- 验证输出完全确定；
- 新评分版本不得修改旧版本回放结果。

## 18. 实施顺序

逐阶段验收条件和可直接交给编码 Agent 的提示词见
[`full-news-impact-scoring-implementation-plan.md`](full-news-impact-scoring-implementation-plan.md)。

设计文档提交不计入业务实施阶段。业务实现按依赖关系合并为 7 个独立提交并可回退：

1. `feat: add impact scoring contracts and kernel`
2. `feat: extract batched news claims`
3. `feat: assess event and stock impact evidence`
4. `feat: route full daily news analysis by impact`
5. `feat: expose impact scoring in radar snapshot`
6. `feat: render ranked news impact signals`
7. `feat: persist point in time impact signals`

实施时先完成纯计算 scorer 和测试，再接入 workflow。不要先修改前端或直接删除 Top 5 限制。

## 19. 第一版完成定义

- 每个可研究事件都有 `event_importance` 和 breakdown；
- 每个股票关系都有正面幅度、负面幅度、置信度和 reason codes；
- 同源转载不会提高事实影响或置信度；
- 正负证据不会被净额隐藏；
- 高影响低可信进入 `verify_first`；
- Pro 路由由固定规则决定；
- 分数完全由代码计算，LLM 不直接给最终分；
- 所有历史结果保存 `scoring_version`；
- 固定输入可以确定性回放；
- 输出明确说明影响分是研究优先级，不是收益预测。

## 20. 方法参考

- A. Craig MacKinlay, *Event Studies in Economics and Finance*：使用事件窗口附近的异常收益衡量事件影响。
- Tim Loughran、Bill McDonald, *When Is a Liability Not a Liability?*：金融文本不能直接使用通用情绪词典。
- Paul C. Tetlock, *Giving Content to Investor Sentiment*：媒体情绪可能影响短期价格和交易量，但不能等同于基本面影响。

这些研究用于定义后续验证方法，不直接作为第一版评分权重来源。第一版权重是可解释的工程先验，必须通过
point-in-time 数据和 walk-forward 验证逐步校准。
