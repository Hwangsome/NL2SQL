from app.entities.column_info import ColumnInfo
from app.models.column_info import ColumnInfoMySQL


class ColumnInfoMapper:
    @staticmethod
    def to_model(column_info: ColumnInfo) -> ColumnInfoMySQL:
        return ColumnInfoMySQL(
            id=column_info.id,
            name=column_info.name,
            type=column_info.type,
            role=column_info.role,
            examples=column_info.examples,
            description=column_info.description,
            alias=column_info.alias,
            table_id=column_info.table_id,
        )

    @staticmethod
    def to_entity(column_info_mysql: ColumnInfoMySQL) -> ColumnInfo:
        return ColumnInfo(
            id=column_info_mysql.id,
            name=column_info_mysql.name,
            type=column_info_mysql.type,
            role=column_info_mysql.role,
            examples=list(column_info_mysql.examples or []),
            description=column_info_mysql.description or "",
            alias=list(column_info_mysql.alias or []),
            table_id=column_info_mysql.table_id,
        )
