from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.column_info import ColumnInfo
from app.entities.column_metric import ColumnMetric
from app.entities.metric_info import MetricInfo
from app.entities.table_info import TableInfo
from app.models.column_info import ColumnInfoMySQL
from app.models.column_metric import ColumnMetricMySQL
from app.models.metric_info import MetricInfoMySQL
from app.models.table_info import TableInfoMySQL
from app.repositories.mysql.meta.mappers.column_info_mapper import ColumnInfoMapper
from app.repositories.mysql.meta.mappers.column_metric_mapper import ColumnMetricMapper
from app.repositories.mysql.meta.mappers.metric_info_mapper import MetricInfoMapper
from app.repositories.mysql.meta.mappers.table_info_mapper import TableInfoMapper


class MetaMySQLRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_table_infos(self, table_infos: list[TableInfo]) -> None:
        for table_info in table_infos:
            await self.session.merge(TableInfoMapper.to_model(table_info))

    async def save_column_infos(self, column_infos: list[ColumnInfo]) -> None:
        for column_info in column_infos:
            await self.session.merge(ColumnInfoMapper.to_model(column_info))

    async def save_metric_infos(self, metric_infos: list[MetricInfo]) -> None:
        for metric_info in metric_infos:
            await self.session.merge(MetricInfoMapper.to_model(metric_info))

    async def save_column_metrics(self, column_metrics: list[ColumnMetric]) -> None:
        for column_metric in column_metrics:
            await self.session.merge(ColumnMetricMapper.to_model(column_metric))

    async def get_column_info_by_id(self, column_id: str) -> ColumnInfo | None:
        result = await self.session.get(ColumnInfoMySQL, column_id)
        return ColumnInfoMapper.to_entity(result) if result else None

    async def get_table_info_by_id(self, table_id: str) -> TableInfo | None:
        result = await self.session.get(TableInfoMySQL, table_id)
        return TableInfoMapper.to_entity(result) if result else None

    async def get_key_columns_by_table_id(self, table_id: str) -> list[ColumnInfo]:
        sql = text(
            """
            select *
            from column_info
            where table_id = :table_id
              and role in ('primary_key', 'foreign_key')
            """
        )
        result = await self.session.execute(sql, {"table_id": table_id})
        return [
            ColumnInfo(
                id=row["id"],
                name=row["name"],
                type=row["type"],
                role=row["role"],
                examples=list(row["examples"] or []),
                description=row["description"] or "",
                alias=list(row["alias"] or []),
                table_id=row["table_id"],
            )
            for row in result.mappings().fetchall()
        ]
