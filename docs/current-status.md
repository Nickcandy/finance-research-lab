# finance-research-lab 当前实现说明

生成日期：2026-06-17

## 现在已经完成什么

当前项目已经完成第一版 MVP 的本地闭环：读取股票池、根据热点新闻标题做规则化追源分析，并生成一份 Markdown 研究报告。项目定位仍然是个人研究辅助和作品集展示，不输出确定性买卖建议，也没有自动交易逻辑。

在此基础上，项目已经补了一层 Agent v0 结构：把原本的单段脚本拆成可观察的 tools + workflow，并记录每一步 `AgentStep`。目前仍是代码控制的确定性流程，后续再接 LLM function calling、RAG、行情和回测。

已完成的核心能力：

- 提供 `finance-lab trace-news` 命令行入口。
- 从 CSV 文件读取关注股票池。
- 基于新闻标题关键词识别主题，例如 AI、数据中心、光模块、稳定币、支付、券商、CXO、商业航天。
- 基于关键词对新闻类型做简单分类，例如资本开支、订单合同、政策监管、业绩指引、产品发布。
- 将股票池标的按主题重合度映射为直接受益、间接受益、情绪映射。
- 为 AI 数据中心链条和稳定币支付链条生成默认产业链路径、付款方、收款方。
- 输出 Markdown 热点追源报告，包含原始新闻、产业链拆解、市场映射、阶段状态、验证点和风险备注。
- 已有最小单元测试覆盖主题识别、股票池映射、报告核心章节和 Agent v0 workflow 执行步骤。

## 当前代码结构

```text
src/finance_research_lab/
  cli.py          # CLI 参数解析和 trace-news 命令执行
  models.py       # WatchlistItem、NewsTrace 等核心数据结构
  agent_models.py # ToolResult、AgentStep、AgentRun
  tools.py        # read_watchlist / trace_news / render_report / write_report 工具封装
  workflow.py     # 代码控制的 Agent v0 workflow
  news_trace.py   # 股票池读取、主题识别、新闻分类、追源构建
  report.py       # Markdown 报告渲染
tests/
  test_news_trace.py
  test_report.py
  test_workflow.py
prompts/
  investment_research_agent.md
data/
  watchlist.example.csv
reports/
  .gitkeep
```

## 主流程

1. 用户执行 `finance-lab trace-news`，传入新闻标题、来源、股票池路径和输出路径。
2. `cli.py` 调用 `load_watchlist()` 读取 CSV 股票池。
3. `build_trace()` 对标题做主题识别和新闻类型分类。
4. `build_trace()` 遍历股票池，根据主题交集把标的分成直接受益、间接受益和情绪映射。
5. `build_trace()` 生成 `NewsTrace` 数据对象。
6. `render_news_trace()` 将 `NewsTrace` 渲染为 Markdown。
7. CLI 创建输出目录并写入报告文件。

## 数据模型

`WatchlistItem` 表示关注标的：

- `symbol`：代码。
- `name`：名称。
- `market`：市场。
- `themes`：主题标签。
- `thesis`：关注逻辑。
- `risks`：风险点。

`NewsTrace` 表示一条热点新闻的追源结果：

- `headline`、`source`：原始新闻信息。
- `news_type`：规则分类后的新闻类型。
- `payer`、`receiver`：产业链中的付款方和收款方。
- `value_chain`：产业链路径。
- `direct_beneficiaries`、`indirect_beneficiaries`、`sentiment_mappings`：股票池映射结果。
- `stage`、`action_state`：当前阶段和动作状态。
- `verification_points`：后续验证清单。

## 规则逻辑

主题识别目前完全基于内置关键词表 `THEME_KEYWORDS`。例如标题中出现 `AI`、`data center`、`capex`、`光模块` 等词，会匹配到 AI、数据中心、光模块等主题。

股票池映射规则很简单：

- 主题交集大于等于 2 个：直接受益。
- 主题交集等于 1 个：间接受益。
- 如果主题词出现在标的 thesis 中：情绪映射。

产业链路径目前只对两个方向有专门模板：

- AI / 数据中心 / 光模块。
- 稳定币 / 支付。

其他主题会落到通用占位路径，需要人工补充判断。

## 命令示例

安装后运行：

```bash
finance-lab trace-news \
  --headline "Microsoft raises AI data center capex guidance" \
  --source "example" \
  --watchlist data/watchlist.example.csv \
  --output reports/demo-news-trace.md
```

不安装脚本时运行：

```bash
PYTHONPATH=src python -m finance_research_lab.cli trace-news \
  --headline "稳定币监管框架推进，支付基础设施受关注" \
  --source "manual" \
  --watchlist data/watchlist.example.csv \
  --output reports/demo-news-trace.md
```

## 已有测试

当前测试覆盖：

- `infer_themes()` 能从 AI capex 标题中识别 AI 和数据中心主题。
- `build_trace()` 能把 AI 数据中心光模块相关标的映射为直接受益。
- `render_news_trace()` 输出热点追源标题、市场映射章节和验证清单。

运行方式：

```bash
pytest
```

## 还没有做什么

当前版本还没有实现以下能力：

- 没有真实新闻 URL 抓取。
- 没有新闻来源时间线和传播链去重。
- 没有行情、财务、估值或成交额数据接入。
- 没有数据库、后端服务或 Web 前端。
- 没有回测、策略信号或自动交易。
- 没有 LLM 摘要或外部数据源适配。

## CodeGraph 状态

本次已在仓库根目录执行 `codegraph init`。初始化结果：

- 索引文件数：7。
- 节点数：41。
- 边数：66。

`.codegraph/` 是本地索引数据库目录，已加入根 `.gitignore`，不参与版本控制。
