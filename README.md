# NL2SQL Demo Workspace

一个可直接演示的中文 `NL2SQL` 项目工作区，包含：

- [data-agent](./data-agent)：后端智能体，基于 `FastAPI + LangGraph + MySQL + Qdrant + Elasticsearch`
- [data-agent-fronted](./data-agent-fronted)：前端对话式数据问答界面，支持流式结论、图表和执行进度详情

## 项目效果

### 首页

![首页截图](./docs/screenshots/home.png)

### 执行过程

![执行过程截图](./docs/screenshots/progress.png)

### 结果展示

![结果展示截图](./docs/screenshots/result.png)

## 功能特性

- 一问一答式数据问答体验
- 流式返回结论，不只是表格结果
- 自动将结果渲染为图表和明细表
- 支持查看 Agent 执行进度，并可点击展开每一步的执行详情
- 支持相对时间解释，例如把“去年”明确解释成具体年份
- 内置较大规模的演示数据，可直接用于对外演示

## 演示数据

项目内已经保留了一套大规模演示数据，位置在 [data/demo_dw_large](./data-agent/data/demo_dw_large)。

默认规模：

- `21` 个地区
- `600` 个客户
- `120` 个商品
- `1186` 个日期
- `18000` 条订单事实

## 目录结构

```text
NL2SQL/
├── data-agent/
│   ├── app/
│   ├── conf/
│   ├── data/
│   ├── docker/
│   └── prompts/
├── data-agent-fronted/
│   ├── app/
│   ├── components/
│   └── lib/
└── docs/
    └── screenshots/
```

## 快速启动

### 1. 启动后端基础设施和 Agent

```bash
cd /Users/bill/code/AI/NL2SQL/data-agent
docker compose up -d mysql qdrant elasticsearch
docker compose up -d agent
```

### 2. 启动前端

```bash
cd /Users/bill/code/AI/NL2SQL/data-agent-fronted
pnpm install
pnpm start --hostname 127.0.0.1 --port 3000
```

### 3. 访问页面

- 前端：[http://127.0.0.1:3000](http://127.0.0.1:3000)
- 后端健康检查：[http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

## 示例问题

- `统计去年各地区的销售总额`
- `统计华东地区销售总额`
- `按品牌统计销售额`
- `按会员等级统计客单价`

## 技术栈

- Backend: `FastAPI`, `LangGraph`, `SQLAlchemy`, `MySQL`, `Qdrant`, `Elasticsearch`
- Frontend: `Next.js`, `React`, `TypeScript`, `Tailwind CSS`, `Recharts`
- Model Access: `OpenAI-compatible LLM`, `OpenAI embeddings`
