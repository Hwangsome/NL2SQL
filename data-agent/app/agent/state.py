from typing import Any, NotRequired, TypedDict

from app.entities.column_info import ColumnInfo
from app.entities.metric_info import MetricInfo
from app.entities.value_info import ValueInfo


class ColumnInfoState(TypedDict):
    name: str
    type: str
    role: str
    examples: list[Any]
    description: str
    alias: list[str]


class TableInfoState(TypedDict):
    name: str
    role: str
    description: str
    columns: list[ColumnInfoState]


class MetricInfoState(TypedDict):
    name: str
    description: str
    relevant_columns: list[str]
    alias: list[str]


class DateInfoState(TypedDict):
    date: str
    weekday: str
    quarter: str
    year: int
    month: int
    last_year: int
    current_quarter: str


class DBInfoState(TypedDict):
    dialect: str
    version: str


class DataAgentState(TypedDict):
    query: str
    keywords: NotRequired[list[str]]
    retrieved_columns: NotRequired[list[ColumnInfo]]
    retrieved_values: NotRequired[list[ValueInfo]]
    retrieved_metrics: NotRequired[list[MetricInfo]]
    table_infos: NotRequired[list[TableInfoState]]
    metric_infos: NotRequired[list[MetricInfoState]]
    date_info: NotRequired[DateInfoState]
    db_info: NotRequired[DBInfoState]
    sql: NotRequired[str]
    result_rows: NotRequired[list[dict[str, Any]]]
    answer: NotRequired[str]
    error: NotRequired[str | None]
