"""
MetaKnowledgeService 模块说明（构建节点）

作用：
- 负责把 DW（业务数据库）中的可用元数据，离线构建成 NL2SQL 运行时可直接消费的知识资产。

达到的效果：
- 在 Meta MySQL 中沉淀结构化元数据真相（表/字段/指标/关系）。
- 在 Qdrant 中构建语义向量索引（字段与指标的 name/description/alias）。
- 在 Elasticsearch 中构建值索引（value -> column_id），用于值反查字段。

最终收益：
- 在线问答阶段无需实时扫描数据库结构，只做检索与推理，响应更快、结果更稳。
- 同时兼顾三类能力：结构化约束（MySQL）、语义召回（Qdrant）、值级匹配（ES）。

为什么要“向量检索 + ES 检索”一起用（直白版）：
- Qdrant 负责“词不一样但意思接近”的问题：
  - 例如用户说“销售额”，字段可能叫 `order_amount`；
  - 用户说“品类”，字段可能叫 `category_name`。
- ES 负责“用户说的是一个具体值”的问题：
  - 例如“华东”“已支付”“苹果”这类词，通常是字段值，不是字段名。
- 两者组合后，系统既能知道“可能是哪一列”（语义召回），
  也能知道“这次条件值落在哪一列”（值命中），从而更稳地生成 where/join。
"""

import uuid
from pathlib import Path

from omegaconf import OmegaConf

from app.clients.embedding_client_manager import EmbeddingClientProtocol
from app.conf.meta_config import MetaConfig
from app.core.log import logger
from app.entities.column_info import ColumnInfo
from app.entities.column_metric import ColumnMetric
from app.entities.metric_info import MetricInfo
from app.entities.table_info import TableInfo
from app.entities.value_info import ValueInfo
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository


class MetaKnowledgeService:
    """
    负责把 DW 中的结构化信息构建为 NL2SQL 可用的三类知识资产。

    为什么要拆成三份存储：
    - Meta MySQL：存“标准化元数据事实”（表/字段/指标及关系），并保存字段示例值（examples），
      用于可追踪、可治理、可审计。
    - Qdrant：存“可语义检索的向量索引”（字段/指标 name、description、alias 的 embedding），
      同时 payload 内也带有字段示例值（来自 ColumnInfo.examples），
      用于把用户业务语言召回到候选字段/指标。
    - Elasticsearch：存“字段示例值/候选值倒排索引”（例如地区名、商品名等离散值），
      用于值级别的快速匹配与召回（不是向量语义检索）。

    这三者组合后，运行时既有结构化约束，又有语义召回能力，还能处理具体取值匹配。

    设计取舍（为什么不只用一个库）：
    - 不只用 MySQL：MySQL 擅长结构化关系，但不擅长语义相似召回。
    - 不只用 Qdrant：向量检索擅长“找相近”，但不适合作为唯一真相源管理关系与治理。
    - 不只用 ES：ES 擅长关键词/倒排检索，但对同义语义（如“销售额”≈“order_amount”）不稳定。
    - 三层分工可让构建与运行各司其职：离线构建成本可控，在线检索延迟更低且结果更稳。

    再换一种业务视角理解“Qdrant + ES”：
    - 如果只有 Qdrant：
      - 能较好处理“销售额≈order_amount”；
      - 但对“华东”这种具体取值，未必总能稳定定位到 `dim_region.region_name`。
    - 如果只有 ES：
      - 能较好命中“华东/已支付/苹果”等具体值；
      - 但对“销售额/成交金额/GMV”这类同义语义泛化较弱。
    - 两者并行召回再合并：
      - Qdrant 给“候选字段/指标范围”；
      - ES 给“值 -> 字段”的硬映射；
      - 最终 SQL 更容易同时选对列名和过滤条件。
    """
    def __init__(
        self,
        embedding_client: EmbeddingClientProtocol,
        column_qdrant_repository: ColumnQdrantRepository,
        value_es_repository: ValueESRepository,
        metric_qdrant_repository: MetricQdrantRepository,
        meta_mysql_repository: MetaMySQLRepository,
        dw_mysql_repository: DWMySQLRepository,
    ):
        self.embedding_client = embedding_client
        self.column_qdrant_repository = column_qdrant_repository
        self.value_es_repository = value_es_repository
        self.metric_qdrant_repository = metric_qdrant_repository
        self.meta_mysql_repository = meta_mysql_repository
        self.dw_mysql_repository = dw_mysql_repository

    async def _save_tables_to_meta_db(self, meta_config: MetaConfig) -> list[ColumnInfo]:
        # 第 1 层：写 Meta MySQL（结构化真相层）
        #
        # 目标：
        # - 把 YAML 中“允许被问数系统使用”的表/字段定义，落成结构化元数据。
        # - 同时从 DW 补充字段真实类型、示例值，提升可解释性和可用性。
        #
        # 输入：
        # - meta_config.tables（业务配置：描述、别名、字段角色等）
        # - DW information_schema（真实字段类型）
        # - DW 样例值（examples）
        #
        # 输出：
        # - TableInfo 列表（表级语义）
        # - ColumnInfo 列表（字段级语义 + examples）
        #
        # 为什么先写这一层：
        # - 它是后续 Qdrant / ES 构建的“统一事实基线”；
        # - 先有结构化真相，后续索引才不会出现“索引里有、元数据里无”的不一致。
        #
        # 示例：
        # - DW 字段：fact_order.order_amount (DECIMAL)
        # - 配置描述：销售额
        # - examples：["128.5", "999.0"]
        # - 最终会形成一个 ColumnInfo，供 Qdrant payload 与 ES 映射复用。
        table_infos: list[TableInfo] = []
        column_infos: list[ColumnInfo] = []

        for table in meta_config.tables:
            table_infos.append(
                TableInfo(
                    id=table.name,
                    name=table.name,
                    role=table.role,
                    description=table.description,
                )
            )

            dw_columns = await self.dw_mysql_repository.get_table_columns(table.name)
            config_columns = {column.name: column for column in table.columns}

            for dw_column in dw_columns:
                column_name = dw_column["column_name"]
                # 只同步配置中声明过的字段，避免把“技术字段/脏字段/不开放字段”暴露给问数链路。
                if column_name not in config_columns:
                    continue
                column_config = config_columns[column_name]
                # examples 让字段语义更可解释（例如地区字段出现“华东/华北”），
                # 下游在值识别、提示词构造、日志排查时都会更有业务上下文。
                examples = await self.dw_mysql_repository.get_column_examples(table.name, column_name)
                column_infos.append(
                    ColumnInfo(
                        id=f"{table.name}.{column_name}",
                        name=column_name,
                        type=str(dw_column["data_type"]),
                        role=column_config.role,
                        examples=examples,
                        description=column_config.description,
                        alias=column_config.alias,
                        table_id=table.name,
                    )
                )

        async with self.meta_mysql_repository.session.begin():
            await self.meta_mysql_repository.save_table_infos(table_infos)
            await self.meta_mysql_repository.save_column_infos(column_infos)

        return column_infos

    async def _save_column_info_to_qdrant(self, column_infos: list[ColumnInfo]) -> None:
        # 第 2 层（字段）：写 Qdrant 向量库（语义召回层）
        #
        # 目标：
        # - 把“字段的多种表达方式”向量化，提升自然语言问法到字段的召回率。
        #
        # 存储策略：
        # - 向量文本：name / description / alias（一个字段可对应多条向量点）
        # - payload：完整 ColumnInfo（包含 examples）
        #
        # 为什么这样存：
        # - 用户问“销售额”，字段名可能叫 order_amount；
        # - 用户问“类目”，字段可能叫 category_name；
        # - 单一文本入口覆盖率不足，所以要多入口语义召回。
        #
        # 命中后收益：
        # - 虽然命中的是某条向量点，但可直接拿到同一个 ColumnInfo payload，
        #   下游不需要再额外 join 元数据。
        await self.column_qdrant_repository.ensure_collection()

        points: list[dict] = []
        for column_info in column_infos:
            # 同一个字段拆成多条向量点：
            # - name 负责命中“接近字段名”的问法
            # - description 负责命中“业务语义表达”
            # - alias 负责命中“口语/同义词/内部简称”
            # 但 payload 统一回指同一个 ColumnInfo，保证召回后仍是“一个字段实体”。
            points.append({"id": str(uuid.uuid4()), "embedding_text": column_info.name, "payload": column_info})
            points.append(
                {"id": str(uuid.uuid4()), "embedding_text": column_info.description, "payload": column_info}
            )
            for alias in column_info.alias:
                points.append({"id": str(uuid.uuid4()), "embedding_text": alias, "payload": column_info})

        # 过滤空文本，避免产生无意义向量点；ids/payload/embedding_text 一一对应。
        embedding_texts = [point["embedding_text"] for point in points if point["embedding_text"]]
        payloads = [point["payload"] for point in points if point["embedding_text"]]
        ids = [point["id"] for point in points if point["embedding_text"]]

        embeddings: list[list[float]] = []
        batch_size = 10
        for index in range(0, len(embedding_texts), batch_size):
            # 分批 embedding 是为了控制外部模型调用的吞吐和内存占用，降低超时风险。
            batch = embedding_texts[index : index + batch_size]
            embeddings.extend(await self.embedding_client.aembed_documents(batch))

        await self.column_qdrant_repository.upsert(ids, embeddings, payloads)

    async def _save_value_info_to_es(self, meta_config: MetaConfig, column_infos: list[ColumnInfo]) -> None:
        # 第 3 层：写 ES 值索引（值匹配层）
        #
        # 目标：
        # - 建立“值 -> 字段”的可检索映射，用于反查值最可能属于哪个字段。
        #
        # 存储内容：
        # - ValueInfo(id, value, column_id)
        # - 例如：
        #   - value="华东", column_id="dim_region.region_name"
        #   - value="已支付", column_id="fact_order.order_status"
        #
        # 一个更完整的 ES 文档示例（对应 ValueInfo）：
        # - id: "dim_region.region_name.华东"
        # - value: "华东"
        # - column_id: "dim_region.region_name"
        #
        # 写入 ES 后，该文档会作为一条可全文检索记录存在于值索引中。
        # 这意味着后续 `recall_value` 节点用关键词 `华东` 做 `match value` 时，
        # 可以直接命中这条记录，并拿回它绑定的 `column_id`。
        #
        # 为什么需要这一层：
        # - 向量召回擅长语义近似，但对“具体值命中”并非最优；
        # - ES 倒排检索在离散值匹配上更直接，能快速把值回连到字段。
        #
        # 为什么只同步 sync=true：
        # - 不是所有字段都需要值索引；
        # - 避免索引膨胀、构建时间过长、无效噪声值影响召回。
        await self.value_es_repository.ensure_index()

        column_to_sync = {
            f"{table.name}.{column.name}": column.sync
            for table in meta_config.tables
            for column in table.columns
        }

        value_infos: list[ValueInfo] = []
        for column_info in column_infos:
            # 只为明确开启 sync 的字段建立值索引：
            # - 不是所有字段都需要值召回
            # - 可减少 ES 索引体积和构建耗时
            if not column_to_sync.get(column_info.id):
                continue

            # 这里从 DW 拉取“可出现的真实值集合”，它与 ColumnInfo.examples 语义一致，
            # 但用途不同：examples 偏“解释字段”，ES value 偏“检索字段”。
            values = await self.dw_mysql_repository.get_column_values(
                table_name=column_info.table_id,
                column_name=column_info.name,
            )
            # ValueInfo 是“值 -> 字段”的映射单元，用于把问题中的具体值回连到字段。
            #
            # 典型链路：
            # - 用户问题中识别到“华东”
            # - 在 ES 命中 value="华东"
            # - 回拿 column_id="dim_region.region_name"
            # - 下游据此增强 where 条件字段选择
            #
            # 结合后续节点再展开为：
            # 1) `recall_value`：对 query 扩词后，逐词检索 ES，得到 ValueInfo 列表
            # 2) `merge_retrieved_info`：把 ValueInfo 反向补到字段集合中
            #    - 若字段尚未被字段向量召回命中，会按 column_id 去 Meta 库补齐字段
            #    - 并把 value 追加到字段 examples，增强“值-字段”对应关系
            # 3) `filter_table` / `generate_sql`：在更小上下文中生成 where 条件
            #    - 例如把“华东”落到 `dim_region.region_name = '华东'`
            #
            # 为什么“通过值”能召回到相关表和字段：
            # - 因为 ValueInfo 里不是只存 value 文本，还显式存了 column_id；
            # - column_id 是 `table.column` 形式（如 `dim_region.region_name`）；
            # - 命中 value 后，系统能直接定位到字段，进而定位到所属表（dim_region）。
            value_infos.extend(
                ValueInfo(
                    id=f"{column_info.id}.{value}",
                    value=value,
                    column_id=column_info.id,
                )
                for value in values
            )

        await self.value_es_repository.index(value_infos)

    async def _save_metrics_to_meta_db(self, meta_config: MetaConfig) -> list[MetricInfo]:
        # 指标同样先落 Meta MySQL，形成可治理的“指标真相层”。
        # relevant_columns 会被保存为关联关系，支撑后续 SQL 生成时的字段约束。
        #
        # 示例：
        # - 指标：销售额（GMV）
        # - relevant_columns: ["fact_order.order_amount", "fact_order.order_status"]
        # - 含义：后续生成 SQL 时，模型可优先在这些关联字段里组织表达。
        metric_infos: list[MetricInfo] = []
        column_metrics: list[ColumnMetric] = []

        for metric in meta_config.metrics:
            metric_infos.append(
                MetricInfo(
                    id=metric.name,
                    name=metric.name,
                    description=metric.description,
                    relevant_columns=metric.relevant_columns,
                    alias=metric.alias,
                )
            )
            column_metrics.extend(
                ColumnMetric(column_id=relevant_column, metric_id=metric.name)
                for relevant_column in metric.relevant_columns
            )

        async with self.meta_mysql_repository.session.begin():
            await self.meta_mysql_repository.save_metric_infos(metric_infos)
            await self.meta_mysql_repository.save_column_metrics(column_metrics)

        return metric_infos

    async def _save_metric_info_to_qdrant(self, metric_infos: list[MetricInfo]) -> None:
        # 指标向量化策略与字段一致：name/description/alias 多入口召回。
        # 原因是用户问法经常是“GMV/成交额/销售额”混用，单一文本很难覆盖。
        await self.metric_qdrant_repository.ensure_collection()

        points: list[dict] = []
        for metric_info in metric_infos:
            points.append({"id": str(uuid.uuid4()), "embedding_text": metric_info.name, "payload": metric_info})
            points.append(
                {"id": str(uuid.uuid4()), "embedding_text": metric_info.description, "payload": metric_info}
            )
            for alias in metric_info.alias:
                points.append({"id": str(uuid.uuid4()), "embedding_text": alias, "payload": metric_info})

        embedding_texts = [point["embedding_text"] for point in points if point["embedding_text"]]
        payloads = [point["payload"] for point in points if point["embedding_text"]]
        ids = [point["id"] for point in points if point["embedding_text"]]

        embeddings: list[list[float]] = []
        batch_size = 10
        for index in range(0, len(embedding_texts), batch_size):
            batch = embedding_texts[index : index + batch_size]
            embeddings.extend(await self.embedding_client.aembed_documents(batch))

        await self.metric_qdrant_repository.upsert(ids, embeddings, payloads)

    async def build(self, config_path: Path) -> None:
        # 构建顺序：
        # 1) 先写 Meta MySQL（确立标准化元数据）
        # 2) 再基于这些元数据写 Qdrant（语义召回）
        # 3) 最后写 ES 值索引（值匹配）
        # 这样可以保证“语义索引”和“值索引”都以统一的元数据为准，减少不一致。
        # 同时也便于增量重建：当配置变更时，只要重跑该流程即可统一刷新三层资产。
        #
        # 可把这条流程理解为“离线建库”：
        # - 在线问答时只做检索与推理，不做重型元数据扫描与索引构建，
        #   从而降低响应延迟并提高稳定性。
        context = OmegaConf.load(config_path)
        schema = OmegaConf.structured(MetaConfig)
        meta_config: MetaConfig = OmegaConf.to_object(OmegaConf.merge(schema, context))

        logger.info("加载元数据配置完成")

        if meta_config.tables:
            column_infos = await self._save_tables_to_meta_db(meta_config)
            logger.info("保存表和字段信息到 Meta 数据库")
            await self._save_column_info_to_qdrant(column_infos)
            logger.info("字段向量索引构建完成")
            await self._save_value_info_to_es(meta_config, column_infos)
            logger.info("字段取值全文索引构建完成")

        if meta_config.metrics:
            metric_infos = await self._save_metrics_to_meta_db(meta_config)
            logger.info("保存指标信息到 Meta 数据库")
            await self._save_metric_info_to_qdrant(metric_infos)
            logger.info("指标向量索引构建完成")

        logger.info("元数据知识库构建完成")
