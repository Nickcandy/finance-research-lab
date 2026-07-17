# 前端 MVP 分析与实施计划

> 状态：MVP-A 已完成，MVP-B 已完成全量事件目录与单事件按需分析
> 日期：2026-07-17
> 范围：本地单用户 Web MVP，不包含 Task 5 多事件源和 Task 6 Serenity 深度分析

## 1. 结论

当前项目已经能自动生成真实的 Event-driven A 股研究日报，但产品入口仍是 CLI，主要输出仍是
Markdown。下一步应优先补前端产品层，而不是继续扩展更多分析功能。

前端 MVP 的定位是：

> 一个安静、可信、可追溯的“研究晨报 + Agent 工作台”，而不是行情终端或荐股软件。

推荐分成两个里程碑：

1. **MVP-A：真实日报可视化**。增加稳定 JSON snapshot 和只读本地 API，完成好看的“今日雷达”。
2. **MVP-B：本地可操作工作台**。增加一键运行、真实进度、事件详情和运行记录。

MVP-A 已完成。MVP-B 已增加 `/events`、`/events/:id` 和后台单事件分析；整份日报后台生成与运行记录仍未实现。

## 2. 当前状态审计

### 2.1 已具备的内容基础

当前 `daily-radar` 已经提供：

- 最近 24 小时 Top 5 市场事件。
- 事件类型、主题、关键事实和产业链路径。
- 已校验、待确认、风险排除候选。
- watchlist 命中。
- 候选理由、支持证据、风险和验证任务。
- `AgentStep` 执行轨迹和 fallback 信息。
- Markdown 报告以及全部非空来源 URL。

因此，前端不需要重新实现研究逻辑；它应该把现有研究结果重新组织成更容易扫描和下钻的产品界面。

### 2.2 MVP-B 剩余缺口

仓库现在使用 `DailyRadarSnapshot v2.1`：`/today` 展示 Top 5，`/events` 展示全部聚类，单事件分析通过
本地后台任务执行并按 `run_id + event_id` 保存。整份 daily workflow 仍由 CLI 同步启动。

MVP-B 仍需增加逐步回调、运行持久化和后台执行；届时再补 `AgentStep` 的开始/结束时间与独立错误，
用于真实进度和完整运行审计。

### 2.3 本地工具链

当前机器已经具备：

```text
Node.js 24.11.1
npm 10.9.8
pnpm 10.24.0
Python 3.9.6
```

当前 Vite 要求 Node `20.19+` 或 `22.12+`，本机 Node 版本满足要求。Vite 官方提供 `react-ts`
模板，因此无需额外安装 Node 运行时。

参考：

- [Vite Getting Started](https://vite.dev/guide/)
- [Tailwind CSS with Vite](https://tailwindcss.com/docs/installation/using-vite)
- [TanStack Query React](https://tanstack.com/query/latest/docs/framework/react/overview)
- [shadcn/ui for Vite](https://ui.shadcn.com/docs/installation/vite)

## 3. 产品范围

### 3.1 MVP-A：真实日报可视化

首个可见版本只做一个 `/today` 页面：

- 展示最新一次成功日报。
- 展示数据时间窗口和数据新鲜度。
- 展示 Top 5 事件。
- 展示已校验、待确认、风险排除候选。
- 展示 watchlist 命中和明日验证任务。
- 展示来源 URL、fallback 和 warning。
- 覆盖 Loading、Success、Empty、Error 四种状态。

MVP-A 继续在终端运行 `daily-radar`。浏览器只读取真实结果，不提供一个无法反馈进度的假运行按钮。

### 3.2 MVP-B：本地可操作工作台

MVP-B 在真实数据合同稳定后增加：

- `/events/:id` 事件详情。
- `/runs` 运行记录和 AgentStep 时间线。
- “生成今日雷达”按钮。
- 后台执行和真实状态轮询。
- 新一轮生成时继续展示上一份成功日报。
- 失败后保留旧日报，并显示具体失败步骤。

### 3.3 首版明确不做

- 登录、权限、多人协作和云端部署。
- WebSocket、实时行情、K 线和交易功能。
- 买入、卖出、仓位或收益预测。
- 拖拽式自定义 Dashboard。
- watchlist 完整 CRUD。
- 暗色主题。
- PDF 在线预览。
- 港股、美股和多市场切换。
- 回测图表。
- 移动原生 App。
- 为了视觉效果生成没有真实数据支持的 AI 评分。

## 4. 技术方案

### 4.1 前端技术栈

```text
React + Vite
TypeScript strict
Tailwind CSS
TanStack Query + native fetch
lucide-react
Vitest + React Testing Library
```

MVP-A 不需要 Redux、Axios、日期库或图表库。服务端状态交给 TanStack Query，本地界面状态使用 React
自身能力。日期格式使用 `Intl.DateTimeFormat`。

shadcn/ui 只按需引入 `Button`、`Badge`、`Skeleton`、`Sheet` 等少量基础组件，不引入完整模板，
也不让默认 shadcn 风格替代产品自己的设计 token。

### 4.2 仓库布局

```text
web/
  package.json
  pnpm-lock.yaml
  vite.config.ts
  tsconfig.json
  index.html
  src/
    main.tsx
    App.tsx
    api/
      radar.ts
    types/
      radar.ts
    components/
      PageState.tsx
      RadarHeader.tsx
      EventCard.tsx
      CandidateSection.tsx
      ValidationTasks.tsx
      RunSteps.tsx
    pages/
      TodayPage.tsx
      EventPage.tsx
      RunsPage.tsx
    test/
      setup.ts
    styles.css

src/finance_research_lab/
  daily_radar_snapshot.py
  web_api.py

tests/
  test_daily_radar_snapshot.py
  test_web_api.py
```

MVP-A 只启用 `TodayPage`，但保留 `pages/` 边界，避免 MVP-B 增加路由时重排全部组件。

### 4.3 数据流

```text
ThsNewsSource / evidence providers
              ↓
run_daily_radar_workflow
              ↓
DailyRadarSnapshot v1
       ├── reports/daily-radar.md
       └── reports/daily-radar.json
                         ↓
             local Python API :8000
                         ↓
               Vite /api proxy
                         ↓
                React UI :5173
```

Markdown 继续作为可阅读、可分享的研究产物；JSON 是唯一的前端数据源。

### 4.4 为什么先不用 SQLite

MVP-A 只读取最新日报，使用原子写入的 `daily-radar.json` 足够，能最早验证页面是否真的有价值。

MVP-B 增加运行历史和后台状态时，再使用 Python 标准库 SQLite，最小表为：

```text
agent_runs
agent_steps
daily_radars
```

这样不会在尚未验证界面之前，同时引入 UI、API、任务系统和数据库四类风险。

## 5. JSON 合同

禁止直接用 `dataclasses.asdict()` 暴露内部模型。应建立显式、带版本号的前端 DTO。

推荐顶层结构：

```json
{
  "schema_version": "2.1",
  "run": {
    "id": "20260716T153011+0800",
    "status": "succeeded",
    "generated_at": "2026-07-16T15:34:40+08:00",
    "window_start": "2026-07-15T15:30:11+08:00",
    "window_end": "2026-07-16T15:30:11+08:00",
    "warnings": [],
    "steps": []
  },
  "summary": {
    "total_event_count": 514,
    "core_event_count": 5,
    "verified_count": 1,
    "unverified_count": 7,
    "excluded_count": 0,
    "source_count": 1
  },
  "events": [],
  "all_events": [],
  "candidate_groups": {
    "verified": [],
    "unverified": [],
    "excluded": [],
    "watchlist": []
  },
  "validation_tasks": [],
  "disclaimer": "研究辅助，不构成投资建议。"
}
```

每个 event 至少包含：

```text
id / rank / title
latest_published_at
report_count / source_count
sources[] / source_urls[]
event_type / themes[] / key_facts[] / confidence
overall_direction / impact_score
value_chain.payer / receiver / chain_steps[] / direction / reasoning
candidates[]
analysis_status / warnings[]
```

每个 candidate 至少包含：

```text
symbol / name / market
event_ids[]
impact_type / impact_strength
impact_direction / impact_score / confidence
verification_status / verification_source
watchlist_hit
reasoning / evidence[] / risks[]
```

事件 ID 应由稳定输入确定性生成，不使用数组下标。候选分组和伪相关规则在 Python 侧完成，前端只做展示，
避免 Web 与 Markdown 对同一候选得出不同分类。

`all_events` 对纯个股行情使用 `analysis_status=not_applicable` 和
`exclusion_reason=pure_stock_price_update`。详情页仍展示聚类成员，但隐藏分析按钮并说明这是行情结果、
不是可分析的驱动事件。`/today` 增加 Watchlist 风险预警和今日研究候选 Top 10；两者均来自日报生成时
已经完成的分析，不由前端自行评分。

## 6. 最小 API

### MVP-A

```text
GET /api/health
GET /api/radars/latest
```

- `GET /api/health` 返回服务状态和 snapshot 是否存在。
- `GET /api/radars/latest` 返回 `DailyRadarSnapshot v2.1`。
- 尚未生成日报时返回 `404 radar_not_found`。
- snapshot 损坏时返回 `500 invalid_radar_snapshot`，不能吞掉解析错误。

开发环境通过 Vite proxy 把 `/api` 转发到 `http://127.0.0.1:8000`，因此不需要开放任意 CORS。

单事件分析接口：

```text
POST /api/radars/latest/events/{event_id}/analysis
GET  /api/radars/latest/events/{event_id}/analysis
GET  /api/radars/latest/events/{event_id}/report
```

同一时间只运行一个事件分析。结果保存在 `reports/event-analyses/{run_id}/{event_id}.json`，完整聚类输入
保存在 `reports/event-catalogs/{run_id}.json`；按需分析不会改写日报 Top 5 和候选汇总。

### MVP-B

```text
POST /api/runs/daily-radar
GET  /api/runs
GET  /api/runs/{run_id}
GET  /api/radars/{run_id}
```

- POST 返回 `202` 和真实 `run_id`，后台执行 workflow。
- 同一时间只允许一个 daily-radar 运行，重复请求返回 `409 run_in_progress`。
- GET run 返回真实已完成步骤，不使用估算百分比。
- 本地任务进程意外退出后，遗留的 `running` 状态要转成 `interrupted`。
- MVP 只绑定 `127.0.0.1`，不默认开放局域网访问。

## 7. 信息架构

### 7.1 `/today` 今日雷达

桌面端采用 8/4 双栏，而不是满屏 KPI 卡片：

```text
左侧导航
├─ 今日雷达
└─ 运行记录（MVP-B）

主区域
├─ 日期、24h 时间窗、数据新鲜度、生成按钮（MVP-B）
├─ 紧凑摘要条：热点事件 / 已校验 / 待确认 / 独立来源
├─ 左 8 栏：Top 5 事件流
└─ 右 4 栏：候选研究队列 + 明日验证任务
```

事件卡首页只展示：

- 排名和标题。
- 最新时间与独立来源数。
- 事件类型与 2–3 个主题。
- 一句话产业链路径。
- 已校验/待确认候选数量。
- fallback 或 warning 标识。

完整 URL、长理由、风险和所有证据放到展开区或事件详情，不能把 Markdown 长文原样塞进首页。

### 7.2 `/events` 全部事件

- 展示最近 24 小时全部确定性聚类，按独立来源和新鲜度排序。
- 支持标题、成员新闻和来源搜索；初始 50 条，每次继续加载 50 条。
- 标记 Top 5 核心事件以及未分析、分析中、已分析、失败状态。

### 7.3 `/events/:id` 事件详情

MVP-B 事件详情按研究过程组织：

1. **发生了什么**：关键事实、时间、来源和原文链接。
2. **如何传导**：payer、receiver 和横向产业链节点。
3. **影响谁**：候选、影响方向、强度、验证状态和 watchlist。
4. **为什么**：支持证据、反方证据和风险。
5. **还缺什么**：验证任务。
6. **如何得到结论**：对应 AgentStep。

当前没有 Serenity 稀缺层级时，只展示已有 `chain_steps`，不得伪造稀缺性评分。

### 7.4 `/runs` 运行记录

- 运行时间、数据窗口、状态、耗时和事件数量。
- 步骤时间线：`fetch → cluster → rank → analyze → verify → render → write`。
- 失败步骤显示原始错误和重试入口。
- 新任务运行时继续显示上一份成功日报，并明确标记“新一轮生成中”。

## 8. 视觉方向

### 8.1 设计关键词

```text
可信
安静
编辑部感
高信息密度但不拥挤
证据优先
可追溯
```

不要做成黑底荧光绿的交易终端，也不要套用充满渐变和发光效果的通用 AI Dashboard。

### 8.2 颜色

```text
页面底色       #F5F3EE
内容面         #FFFFFF
主文字         #17201E
次文字         #68706C
分割线         #DCD9D1
主强调         #295F55
信息蓝         #355D8A
待确认琥珀     #A56A1B
风险砖红       #9A4D44
排除灰         #7A7F7C
```

红绿只在明确表达 A 股涨跌方向时使用。校验状态必须同时使用文字、图标和颜色，避免把“验证通过”误读成
“股价上涨”。

### 8.3 排版和空间

- 字体：`Inter, PingFang SC, Noto Sans SC, system-ui, sans-serif`。
- 页面标题：`30/36`。
- 区块标题：`20/28`。
- 正文：`15/24`。
- 元信息：`12/18`。
- 数字启用 tabular numerals。
- 使用 8px 间距体系。
- 卡片圆角 10–12px。
- 主要靠边线和留白分区；只在浮层或 hover 时使用轻阴影。

### 8.4 让页面真正好看的方法

1. 首页只展示决策摘要，长证据渐进展开。
2. 同一页面只使用一个主强调色。
3. 状态 badge 的形状、文案和颜色保持一致。
4. 产业链用简洁的横向节点，而不是复杂关系图。
5. 风险和反方理由不能为了整洁被隐藏。
6. Loading 使用与真实布局一致的 skeleton，避免页面跳动。
7. Empty 和 Error 状态提供明确下一步命令或重试动作。
8. 桌面优先，同时保证窄屏能按“事件 → 候选 → 任务”自然纵向排列。

## 9. 本地运行方式

MVP-A 使用两个本地进程。先生成日报并启动只读 API：

```bash
.venv/bin/finance-lab daily-radar \
  --output reports/daily-radar.md \
  --json-output reports/daily-radar.json

.venv/bin/finance-lab serve --host 127.0.0.1 --port 8000
```

另开终端启动前端：

```bash
cd web
corepack pnpm install
corepack pnpm dev
```

浏览器访问 `http://127.0.0.1:5173/today`。页面通过 Vite `/api` 代理读取真实快照；日报不存在时显示
Empty，快照损坏或 API 不可用时显示 Error。

MVP-B 完成后，可以直接在网页点击“生成今日雷达”；终端命令仍保留，便于调试和自动任务使用。

## 10. 实施任务

### FE-1：冻结 `DailyRadarSnapshot v1`

实现：

- 新增显式 snapshot DTO 和序列化函数。
- 生成稳定 event ID。
- 在 Python 侧完成候选分组和跨事件去重。
- 显式保存 `source_type`、`source_urls` 和实际 provider 证据。
- 保存 warnings、fallback 和 `AgentStep`。
- 原子写入 JSON，不改变现有 Markdown 合同。

验证：

- 固定 fixture 的 JSON 完全稳定。
- 缺失分析、空 URL、fallback 和部分失败均可序列化。
- Markdown 现有测试继续通过。

### FE-2：增加只读本地 API

实现：

- 使用 Python 标准库 `ThreadingHTTPServer`，不增加 Web 框架依赖。
- 新增 `finance-lab serve`。
- 实现 health 和 latest radar 两个 GET API。
- Vite 开发代理固定指向 `127.0.0.1:8000`。

验证：

- 覆盖 success、404、损坏 JSON 和非法 schema version。
- 服务默认不绑定 `0.0.0.0`。

### FE-3：创建前端工程和设计基础

实现：

- 创建 `web/` React + Vite + TypeScript strict。
- 接入 Tailwind Vite plugin、TanStack Query 和 Vitest。
- 定义颜色、排版、间距和状态 token。
- 加入真实 snapshot fixture。

验证：

- `pnpm typecheck`。
- `pnpm lint`。
- `pnpm test`。
- `pnpm build`。

### FE-4：实现 `/today`

实现：

- RadarHeader 和摘要条。
- Top 5 EventCard。
- 候选分组和 watchlist 高亮。
- 验证任务。
- Loading、Success、Empty、Error 状态。
- fallback、warning 和数据过期提示。

验证：

- 真实 snapshot 中所有事件和来源可访问。
- verified、unverified、excluded 不混淆。
- 无日报时显示可复制的生成命令。

### FE-5：真实浏览器视觉验收

实现：

- 使用本地 API 和真实 24 小时日报运行页面。
- 以桌面 1440px 为主，补 1024px 和 390px 响应式。
- 修复溢出、信息密度、对比度和交互问题。

验证：

- 浏览器控制 skill 完成交互检查。
- 保存关键 viewport 截图作视觉基线。
- Loading / Empty / Error / Success 均完成视觉验证。

完成 FE-1 至 FE-5 即达到 MVP-A。

### FE-6：事件详情

实现 `/events/:id`，展示关键事实、产业链、候选证据、风险、URL 和验证任务。

### FE-7：运行持久化和后台执行

实现 SQLite `agent_runs`、`agent_steps`、`daily_radars`，增加 workflow step callback 和单任务后台执行。

### FE-8：运行记录和真实进度

实现 `/runs`、运行按钮、状态轮询、失败保留旧报告和 interrupted 恢复语义。

完成 FE-6 至 FE-8 即达到 MVP-B。

## 11. 测试与验收

### Python

```bash
.venv/bin/python -m pytest -q tests/test_daily_radar_snapshot.py tests/test_web_api.py
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check src tests
```

### 前端

```bash
cd web
pnpm typecheck
pnpm lint
pnpm test
pnpm build
```

必须覆盖：

- Loading / Success / Empty / Error。
- Top 5、来源 URL、候选状态、风险和验证任务。
- fallback 和部分失败。
- 数据过期。
- 运行中仍显示上一份成功日报。
- API 不可用和 snapshot 损坏。
- 桌面、平板和移动窄屏。

### 真实 smoke

1. 用真实数据生成 Markdown 和 JSON。
2. 启动 API 与 Vite。
3. 检查浏览器展示的事件、候选数量和 snapshot 一致。
4. 打开所有来源链接。
5. 验证 fallback、warning 和免责声明可见。
6. 验证刷新页面不会丢失日报。

## 12. 时间估算

| 阶段 | 预计时间 | 结果 |
|---|---:|---|
| FE-1～FE-2 | 2–2.5 天 | 稳定 JSON + 本地 API |
| FE-3～FE-4 | 2.5–3 天 | 可用的今日雷达页面 |
| FE-5 | 0.5–1 天 | 真实视觉验收，MVP-A 完成 |
| FE-6～FE-8 | 3–4 天 | 详情、运行历史和真实进度，MVP-B 完成 |

总计约 8–10 个专注开发日。MVP-A 完成后应先让真实页面接受一次使用反馈，再决定是否调整 MVP-B 的
页面和数据库范围。

## 13. 当前前端实现状态

已完成：

- `web/` React + Vite + TypeScript strict + Tailwind CSS 工程。
- `finance-lab serve`、只读 health/latest API 和 Vite `/api` 代理。
- `/today` 已读取 `reports/daily-radar.json` 的最新成功快照。
- `/today` 的导航、摘要条、Top 5 事件流、候选队列、验证任务和运行审计。
- 事件来源、关键事实、候选证据和风险的渐进展开。
- Loading、Success、Empty、Error 四种状态。
- 1440px、1024px 和 390px 响应式视觉验收。
- `pnpm typecheck`、`pnpm lint`、`pnpm test` 和 `pnpm build`。

尚未完成：

- 当前“刷新快照”只重新读取真实快照，不会执行 Python workflow。
- 事件详情、运行历史、后台执行和真实进度仍属于 MVP-B。

本项目采用 code-first UI，真实浏览器页面是视觉和交互验收标准，不再依赖外部设计工具。
