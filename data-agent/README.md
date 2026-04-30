# 掌柜问数

基于课程文档重建的 `NL2SQL` 工程，包含：

- `FastAPI` SSE 查询接口
- `LangGraph` 问数智能体
- `MySQL(meta/dw)` 元数据与数仓模拟
- `Qdrant` 语义召回
- `Elasticsearch` 字段值全文召回
- `TEI` Embedding 服务

## 当前状态

后端、基础设施、元数据构建链路、提示词与样例数据已落地。前端课程源码未提供，因此仓库内 `frontend/` 仅保留对接说明。

## 快速启动

1. 复制配置：

```bash
cp conf/app_config.yaml.example conf/app_config.yaml
```

2. 按实际情况填写：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `EMBEDDING_MODEL`

3. 启动基础设施：

```bash
docker compose up -d
```

如果希望后端 `agent` 也通过 Docker 启动，直接运行：

```bash
OPENAI_API_KEY=你的密钥 docker compose up -d agent
```

这条命令会自动构建镜像，并先运行一次 `meta-builder` 初始化 Meta/Qdrant/Elasticsearch，再启动 `agent` 接口服务。

4. 安装依赖：

```bash
uv sync
```

5. 构建元数据知识库：

```bash
uv run python -m app.scripts.build_meta_knowledge --config conf/meta_config.yaml
```

6. 启动服务：

```bash
uv run fastapi dev main.py
```

## Qdrant 访问

`docker compose up -d` 会一并启动 `qdrant`，对应配置见 [docker-compose.yaml](/Users/bill/code/AI/NL2SQL/data-agent/docker-compose.yaml)。

默认端口：

- `6333`：HTTP API 和 Dashboard
- `6334`：gRPC

检查是否启动：

```bash
cd /Users/bill/code/AI/NL2SQL/data-agent
docker compose ps qdrant
```

进入 Qdrant UI：

- Dashboard：[http://127.0.0.1:6333/dashboard](http://127.0.0.1:6333/dashboard)
- API 根路径：[http://127.0.0.1:6333](http://127.0.0.1:6333)

如果需要进入容器内部排查：

```bash
docker exec -it data-agent-qdrant sh
```

## 生成业务数据

项目内提供了可留存的大规模零售业务数据生成脚本，会把 CSV 数据写入 [data/retail_dw_large](/Users/bill/code/AI/NL2SQL/data-agent/data/retail_dw_large) 并可直接导入 `dw` 库：

```bash
cd /Users/bill/code/AI/NL2SQL/data-agent
DW_DB_PORT=3307 uv run python -m app.scripts.generate_retail_dw_data --load-db
META_DB_PORT=3307 DW_DB_PORT=3307 ES_PORT=19200 uv run python -m app.scripts.build_meta_knowledge --config conf/meta_config.yaml
```

默认会生成并导入：

- `21` 个地区
- `600` 个客户
- `120` 个商品
- `18000` 条订单

这样更适合验证“按地区、品牌、会员等级、时间趋势”等问数效果。

## 目录

- `app/` 后端代码
- `conf/` 配置文件
- `docker/` 基础设施资源
- `prompts/` 提示词目录
