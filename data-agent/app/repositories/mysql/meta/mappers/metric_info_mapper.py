from app.entities.metric_info import MetricInfo
from app.models.metric_info import MetricInfoMySQL


class MetricInfoMapper:
    @staticmethod
    def to_model(metric_info: MetricInfo) -> MetricInfoMySQL:
        return MetricInfoMySQL(
            id=metric_info.id,
            name=metric_info.name,
            description=metric_info.description,
            relevant_columns=metric_info.relevant_columns,
            alias=metric_info.alias,
        )

    @staticmethod
    def to_entity(metric_info_mysql: MetricInfoMySQL) -> MetricInfo:
        return MetricInfo(
            id=metric_info_mysql.id,
            name=metric_info_mysql.name,
            description=metric_info_mysql.description or "",
            relevant_columns=list(metric_info_mysql.relevant_columns or []),
            alias=list(metric_info_mysql.alias or []),
        )
