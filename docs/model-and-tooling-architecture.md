# 模型接入、上下文控制与 Tool Calling 架构

> 更新时间：2026-06-17

## 结论

后续可以顺滑接 LangChain / LangGraph、不同大模型、上下文控制和 tool calling，但前提是第一版代码从一开始就把三层分开：

```text
业务 workflow：决定研究流程怎么走
LLM adapter：负责调用哪个模型
Tool registry：负责定义可被模型调用的工具
```

第一版先不用直接上 LangChain。先写自己的最小接口，后面再接 LangChain / LangGraph 时，只替换 adapter 和 orchestrator，不重写数据模型、工具函数和报告逻辑。

## 推荐分层

```text
src/finance_research_lab/
  llm/
    base.py          # LLMClient 抽象接口
    openai_client.py # OpenAI-compatible API
    mock_client.py   # 测试用假模型
  agents/
    context.py       # 上下文预算、prompt 拼装、压缩
    tools.py         # ToolSpec、ToolRegistry
    orchestrator.py  # Agent loop / workflow 控制
  tools.py           # 现有确定性工具：读股票池、追源、写报告
  workflow.py        # 代码控制的投资研究流程
```

## LLM 抽象接口

```python
class LLMClient:
    def complete(self, messages, *, model: str, temperature: float = 0.2):
        ...

    def tool_call(self, messages, tools, *, model: str, temperature: float = 0.2):
        ...
```

后续不同模型只实现这个接口：

```text
OpenAIClient
ClaudeClient
DeepSeekClient
QwenClient
GeminiClient
OllamaClient
LangChainClient
```

业务代码只依赖 `LLMClient`，这样换模型不会动 workflow。

## Tool Calling 抽象

工具函数保持普通 Python 函数：

```python
def read_watchlist(path: str) -> list[WatchlistItem]:
    ...

def trace_news(news_items, watchlist):
    ...

def rank_opportunities(events, watchlist):
    ...
```

再额外注册 schema：

```python
ToolSpec(
    name="read_watchlist",
    description="Read local watchlist CSV",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string"}
        },
        "required": ["path"]
    },
    handler=read_watchlist,
)
```

这样同一批工具可以给：

- 自己写的 agent loop；
- OpenAI function calling；
- Claude tool use；
- LangChain tools；
- LangGraph 节点。

## 上下文控制

上下文不要靠无限塞 prompt，要做预算和分层。

```text
System prompt：角色、边界、输出格式
Task prompt：本次任务目标
Market context：新闻、行情摘要、自选股
Retrieved context：检索到的历史报告/公司资料
Tool results：工具返回结果摘要
Output schema：报告格式要求
```

上下文控制模块负责：

1. 控制 token budget；
2. 长新闻先摘要；
3. 行情数据只传统计摘要，不传全量表；
4. 历史报告用 RAG 取 topK；
5. 工具结果落库，prompt 里只放摘要和引用 ID；
6. 报告输出固定结构。

## LangChain / LangGraph 什么时候接

### 第一版不用急着接

V0/V1 用自己的 workflow 更清楚：

```text
read_news
→ read_watchlist
→ trace_news
→ rank_opportunities
→ render_report
→ write_report
```

这样更适合面试解释，也方便测试。

### 什么时候接 LangGraph

当流程出现以下需求时再接：

- 多轮循环：模型根据结果决定下一步；
- 分支：新闻类型不同走不同路径；
- 人工确认：高风险建议需要确认；
- 可恢复状态机：跑到一半失败后恢复；
- 多 Agent：新闻分析、行情分析、风控分析分工。

## 是否需要重构

如果现在直接把业务逻辑写死在某个 LangChain chain 里，后面会难改。

如果现在按上面的分层写，后续只需要小改：

```text
新增 LLMClient 实现
新增 ToolSpec schema
新增 LangGraph orchestrator
复用原来的 tools、models、report、tests
```

也就是说，第一版需要做的是“留接口”，不是一上来重型框架。

## 面试讲法

```text
我没有把业务逻辑绑定到某一个模型或 LangChain。项目里把投资研究 workflow、LLM 调用 adapter、工具注册和上下文管理分开。第一版用代码控制 workflow，保证可测试、可追踪；后续如果要接 OpenAI、Claude、DeepSeek、Qwen 或 LangGraph，只需要实现统一的 LLMClient 和 ToolSpec adapter，底层数据模型、工具函数、报告生成和回测逻辑可以复用。
```

## 下一步实现顺序

1. 保持现有确定性 workflow；
2. 新增 `llm/base.py`，定义 `LLMClient`；
3. 新增 `llm/mock_client.py`，先让测试跑通；
4. 新增 `agents/tools.py`，定义 `ToolSpec` 和 `ToolRegistry`；
5. 把现有 `read_watchlist_tool` 等工具注册进去；
6. V1 再接一个真实 OpenAI-compatible 模型；
7. V2/V3 再考虑 LangGraph。
