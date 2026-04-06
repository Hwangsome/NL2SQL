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
                if column_name not in config_columns:
                    continue
                column_config = config_columns[column_name]
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
        await self.column_qdrant_repository.ensure_collection()

        points: list[dict] = []
        for column_info in column_infos:
            points.append({"id": str(uuid.uuid4()), "embedding_text": column_info.name, "payload": column_info})
            points.append(
                {"id": str(uuid.uuid4()), "embedding_text": column_info.description, "payload": column_info}
            )
            for alias in column_info.alias:
                points.append({"id": str(uuid.uuid4()), "embedding_text": alias, "payload": column_info})

        embedding_texts = [point["embedding_text"] for point in points if point["embedding_text"]]
        payloads = [point["payload"] for point in points if point["embedding_text"]]
        ids = [point["id"] for point in points if point["embedding_text"]]

        embeddings: list[list[float]] = []
        batch_size = 10
        for index in range(0, len(embedding_texts), batch_size):
            batch = embedding_texts[index : index + batch_size]
            embeddings.extend(await self.embedding_client.aembed_documents(batch))

        await self.column_qdrant_repository.upsert(ids, embeddings, payloads)

    async def _save_value_info_to_es(self, meta_config: MetaConfig, column_infos: list[ColumnInfo]) -> None:
        await self.value_es_repository.ensure_index()

        column_to_sync = {
            f"{table.name}.{column.name}": column.sync
            for table in meta_config.tables
            for column in table.columns
        }

        value_infos: list[ValueInfo] = []
        for column_info in column_infos:
            if not column_to_sync.get(column_info.id):
                continue

            values = await self.dw_mysql_repository.get_column_values(
                table_name=column_info.table_id,
                column_name=column_info.name,
            )
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
