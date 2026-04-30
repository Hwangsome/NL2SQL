# 本地启动说明

本文记录 `NL2SQL` 项目在本地调试时的完整启动流程。目标是：依赖服务用 Docker 启动，后端 App 在本机运行，方便在 PyCharm 或终端里打断点调试。

## 端口约定

| 服务 | 地址 | 说明 |
| --- | --- | --- |
| 前端 | `http://127.0.0.1:3000` | Next.js 页面 |
| 后端 App | `http://127.0.0.1:8001` | FastAPI，本地进程运行 |
| 后端健康检查 | `http://127.0.0.1:8001/health` | 返回 `{"status":"ok"}` 表示后端可用 |
| 后端 API 文档 | `http://127.0.0.1:8001/docs` | Swagger UI |
| MySQL | `127.0.0.1:33307` | Docker 容器内端口是 `3306` |
| Qdrant | `http://127.0.0.1:6333` | 向量库 |
| Elasticsearch | `http://127.0.0.1:19200` | 字段取值全文索引 |

说明：后端根路径 `http://127.0.0.1:8001/` 没有页面路由，返回 `404 Not Found` 是正常现象。访问前端页面请打开 `http://127.0.0.1:3000`。

## 前置条件

后端依赖使用 `uv`，前端依赖使用 `pnpm`。

```bash
cd /Users/bill/code/AI/NL2SQL/data-agent
uv sync

cd /Users/bill/code/AI/NL2SQL/data-agent-fronted
pnpm install
```

后端需要可用的 OpenAI 兼容模型配置。默认从 `/Users/bill/code/AI/NL2SQL/data-agent/.env` 读取。

至少需要包含：

```bash
OPENAI_API_KEY=你的密钥
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
OPENAI_MODEL=qwen3.5-flash
EMBEDDING_HOST=openai
EMBEDDING_MODEL=text-embedding-v4
```

## 第一次启动

### 1. 启动 Docker 依赖

```bash
cd /Users/bill/code/AI/NL2SQL/data-agent
docker compose -f docker-compose-local.yaml up -d mysql qdrant elasticsearch
```

检查容器状态：

```bash
docker compose -f docker-compose-local.yaml ps
```

期望看到：

- `data-agent-local-mysql` 是 `healthy`
- `data-agent-local-es` 是 `healthy`
- `data-agent-local-qdrant` 是 `Up`

### 2. 构建元数据知识库

第一次启动，或修改了 `conf/meta_config.yaml`、初始化 SQL、样例数据后，需要重新构建知识库。

```bash
cd /Users/bill/code/AI/NL2SQL/data-agent

META_DB_HOST=127.0.0.1 META_DB_PORT=33307 \
DW_DB_HOST=127.0.0.1 DW_DB_PORT=33307 \
QDRANT_HOST=127.0.0.1 QDRANT_PORT=6333 \
ES_HOST=127.0.0.1 ES_PORT=19200 \
EMBEDDING_HOST=openai \
uv run python -m app.scripts.build_meta_knowledge --config conf/meta_config.yaml
```

成功时会看到类似日志：

```text
加载元数据配置完成
保存表和字段信息到 Meta 数据库
字段向量索引构建完成
字段取值全文索引构建完成
保存指标信息到 Meta 数据库
指标向量索引构建完成
元数据知识库构建完成
```

### 3. 启动后端 App

```bash
cd /Users/bill/code/AI/NL2SQL/data-agent

META_DB_HOST=127.0.0.1 META_DB_PORT=33307 \
DW_DB_HOST=127.0.0.1 DW_DB_PORT=33307 \
QDRANT_HOST=127.0.0.1 QDRANT_PORT=6333 \
ES_HOST=127.0.0.1 ES_PORT=19200 \
EMBEDDING_HOST=openai \
uv run uvicorn main:app --host 127.0.0.1 --port 8001
```

验证：

```bash
curl http://127.0.0.1:8001/health
```

期望输出：

```json
{"status":"ok"}
```

### 4. 启动前端

```bash
cd /Users/bill/code/AI/NL2SQL/data-agent-fronted

NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8001 \
pnpm dev --hostname 127.0.0.1 --port 3000
```

访问：

```text
http://127.0.0.1:3000
```

## 日常启动

如果 Docker 数据卷还在，并且没有修改元数据配置或初始化数据，通常不需要重新构建知识库。

启动顺序：

```bash
cd /Users/bill/code/AI/NL2SQL/data-agent
docker compose -f docker-compose-local.yaml up -d mysql qdrant elasticsearch
```

```bash
cd /Users/bill/code/AI/NL2SQL/data-agent

META_DB_HOST=127.0.0.1 META_DB_PORT=33307 \
DW_DB_HOST=127.0.0.1 DW_DB_PORT=33307 \
QDRANT_HOST=127.0.0.1 QDRANT_PORT=6333 \
ES_HOST=127.0.0.1 ES_PORT=19200 \
EMBEDDING_HOST=openai \
uv run uvicorn main:app --host 127.0.0.1 --port 8001
```

```bash
cd /Users/bill/code/AI/NL2SQL/data-agent-fronted

NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8001 \
pnpm dev --hostname 127.0.0.1 --port 3000
```

## 后台启动前端

如果希望前端脱离当前终端运行，可以用 `tmux`：

```bash
tmux new-session -d -s nl2sql-frontend \
  'cd /Users/bill/code/AI/NL2SQL/data-agent-fronted && NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8001 pnpm exec next dev --hostname 127.0.0.1 --port 3000'
```

查看前端日志：

```bash
tmux attach -t nl2sql-frontend
```

停止前端：

```bash
tmux kill-session -t nl2sql-frontend
```

## PyCharm 调试后端

### 调试 FastAPI App

新建 Python Run/Debug Configuration。

推荐配置：

```text
Run target: module
Module name: uvicorn
Parameters: main:app --host 127.0.0.1 --port 8001
Working directory: /Users/bill/code/AI/NL2SQL/data-agent
Python interpreter: /Users/bill/code/AI/NL2SQL/data-agent/.venv/bin/python
Run with `uv run`: 开启
```

Environment variables：

```text
META_DB_HOST=127.0.0.1;META_DB_PORT=33307;DW_DB_HOST=127.0.0.1;DW_DB_PORT=33307;QDRANT_HOST=127.0.0.1;QDRANT_PORT=6333;ES_HOST=127.0.0.1;ES_PORT=19200;EMBEDDING_HOST=openai
```

不要把下面整条命令填进 `Script path`：

```bash
uv run uvicorn main:app --host 127.0.0.1 --port 8001
```

PyCharm 的 `Script path` 需要真实 `.py` 文件路径。要运行 `uvicorn`，应使用 `module` 方式。

### 调试知识库构建脚本

如果需要在 PyCharm 里调试知识库构建脚本，使用：

```text
Run target: module
Module name: app.scripts.build_meta_knowledge
Parameters: --config conf/meta_config.yaml
Working directory: /Users/bill/code/AI/NL2SQL/data-agent
Python interpreter: /Users/bill/code/AI/NL2SQL/data-agent/.venv/bin/python
Run with `uv run`: 开启
```

Environment variables 同上。

## 验证闭环

后端启动后，可以直接请求 SSE 接口验证 Agent 链路：

```bash
curl -N --max-time 180 http://127.0.0.1:8001/api/query \
  -H 'Content-Type: application/json' \
  -H 'Accept: text/event-stream' \
  -d '{"query":"统计去年各地区的销售总额"}'
```

成功时会持续看到：

- `抽取关键字`
- `召回字段`
- `召回指标`
- `召回字段取值`
- `生成SQL`
- `验证SQL`
- `执行SQL`
- `生成结论`
- 最终 `result` 事件

示例 SQL：

```sql
SELECT r.region_name, SUM(f.order_amount) AS gmv
FROM fact_order f
JOIN dim_region r ON f.region_id = r.region_id
JOIN dim_date d ON f.date_id = d.date_id
WHERE d.year = 2025
GROUP BY r.region_name
ORDER BY gmv DESC
```

## 停止服务

停止前端：

```bash
tmux kill-session -t nl2sql-frontend
```

如果前端是在普通终端里启动的，直接按 `Ctrl+C`。

停止后端：

```bash
# 如果后端在普通终端里启动，直接 Ctrl+C。
# 如果后端是后台进程，可按端口查找并停止：
lsof -nP -iTCP:8001 -sTCP:LISTEN
kill <PID>
```

停止 Docker 依赖：

```bash
cd /Users/bill/code/AI/NL2SQL/data-agent
docker compose -f docker-compose-local.yaml down
```

如果要连数据卷一起删除，才使用：

```bash
docker compose -f docker-compose-local.yaml down -v
```

## 常见问题

### 打开 `http://127.0.0.1:8001/` 返回 404

这是正常现象。`8001` 是后端 API，不是前端页面。

请访问：

```text
http://127.0.0.1:8001/health
http://127.0.0.1:8001/docs
http://127.0.0.1:3000
```

### 前端页面第一次打开很慢

如果页面卡在编译阶段，先看前端日志：

```bash
tmux capture-pane -t nl2sql-frontend -p | tail -n 120
```

项目已经避免依赖 `next/font/google` 拉取 Google Fonts。本地启动时不应再因为 `fonts.googleapis.com` 不可用而长时间等待。

### `8001` 或 `3000` 端口被占用

检查端口：

```bash
lsof -nP -iTCP:8001 -sTCP:LISTEN
lsof -nP -iTCP:3000 -sTCP:LISTEN
```

可以换端口启动，例如前端改为 `3001`：

```bash
cd /Users/bill/code/AI/NL2SQL/data-agent-fronted

NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8001 \
pnpm dev --hostname 127.0.0.1 --port 3001
```

### Qdrant 客户端版本 warning

启动后端或构建知识库时，可能看到：

```text
Qdrant client version 1.17.1 is incompatible with server version 1.13.4
```

当前闭环验证可正常运行。后续可以统一升级 Docker 镜像或调整 Python 客户端版本消除 warning。

### TEI Embedding 容器启动失败

`docker-compose-local.yaml` 默认不启动 TEI embedding 容器，默认使用 `.env` 中的 OpenAI 兼容 embedding。

如果要尝试 TEI：

```bash
cd /Users/bill/code/AI/NL2SQL/data-agent
docker compose -f docker-compose-local.yaml --profile tei up -d embedding
```

注意：构建知识库和后端查询必须使用同一个 embedding 模型，否则 Qdrant 向量召回效果会不稳定。
