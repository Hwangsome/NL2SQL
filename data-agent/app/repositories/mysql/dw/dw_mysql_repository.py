from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.sql_safety import ensure_safe_select


class DWMySQLRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_table_columns(self, table_name: str) -> list[dict[str, Any]]:
        sql = text(
            """
            select column_name, data_type
            from information_schema.columns
            where table_schema = database()
              and table_name = :table_name
            order by ordinal_position
            """
        )
        result = await self.session.execute(sql, {"table_name": table_name})
        return [self._normalize_row(row) for row in result.mappings().fetchall()]

    async def get_column_examples(self, table_name: str, column_name: str, limit: int = 3) -> list[Any]:
        sql = text(
            f"""
            select distinct `{column_name}` as value
            from `{table_name}`
            where `{column_name}` is not null
            limit {limit}
            """
        )
        result = await self.session.execute(sql)
        return [self._json_safe(self._normalize_row(row)["value"]) for row in result.mappings().fetchall()]

    async def get_column_values(self, table_name: str, column_name: str, limit: int = 100000) -> list[str]:
        sql = text(
            f"""
            select distinct `{column_name}` as value
            from `{table_name}`
            where `{column_name}` is not null
            limit {limit}
            """
        )
        result = await self.session.execute(sql)
        return [str(self._json_safe(self._normalize_row(row)["value"])) for row in result.mappings().fetchall()]

    async def get_db_info(self) -> dict[str, str]:
        result = await self.session.execute(text("select version() as version"))
        version = result.scalar_one()
        dialect = self.session.get_bind().dialect.name
        return {"version": version, "dialect": dialect}

    async def validate_sql(self, sql: str) -> None:
        ensure_safe_select(sql)
        await self.session.execute(text(f"explain {sql}"))

    async def execute_sql(self, sql: str) -> list[dict[str, Any]]:
        ensure_safe_select(sql)
        result = await self.session.execute(text(sql))
        return [self._normalize_row(row) for row in result.mappings().fetchall()]

    @staticmethod
    def _normalize_row(row: Any) -> dict[str, Any]:
        return {str(key).lower(): value for key, value in dict(row).items()}

    @staticmethod
    def _json_safe(value: Any) -> Any:
        if isinstance(value, Decimal):
            return float(value)
        return value
