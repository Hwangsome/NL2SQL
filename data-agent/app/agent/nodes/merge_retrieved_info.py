from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.progress import emit_progress, preview_list
from app.agent.state import ColumnInfoState, DataAgentState, MetricInfoState, TableInfoState
from app.core.log import logger
from app.entities.column_info import ColumnInfo
from app.entities.table_info import TableInfo


async def merge_retrieved_info(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    writer = runtime.stream_writer
    emit_progress(writer, "合并召回信息", "running", "正在合并字段、字段值和指标召回结果。")

    retrieved_columns = state.get("retrieved_columns", [])
    retrieved_values = state.get("retrieved_values", [])
    retrieved_metrics = state.get("retrieved_metrics", [])
    meta_mysql_repository = runtime.context["meta_mysql_repository"]

    try:
        retrieved_columns_map: dict[str, ColumnInfo] = {
            retrieved_column.id: retrieved_column for retrieved_column in retrieved_columns
        }

        for retrieved_metric in retrieved_metrics:
            for relevant_column in retrieved_metric.relevant_columns:
                if relevant_column not in retrieved_columns_map:
                    column_info = await meta_mysql_repository.get_column_info_by_id(relevant_column)
                    if column_info is not None:
                        retrieved_columns_map[relevant_column] = column_info

        for retrieved_value in retrieved_values:
            column_id = retrieved_value.column_id
            column_value = retrieved_value.value
            if column_id not in retrieved_columns_map:
                column_info = await meta_mysql_repository.get_column_info_by_id(column_id)
                if column_info is not None:
                    retrieved_columns_map[column_id] = column_info
            if column_id in retrieved_columns_map and column_value not in retrieved_columns_map[column_id].examples:
                retrieved_columns_map[column_id].examples.append(column_value)

        table_to_columns_map: dict[str, list[ColumnInfo]] = {}
        for column in retrieved_columns_map.values():
            table_to_columns_map.setdefault(column.table_id, []).append(column)

        for table_id in list(table_to_columns_map.keys()):
            key_columns = await meta_mysql_repository.get_key_columns_by_table_id(table_id)
            existing_ids = {column.id for column in table_to_columns_map[table_id]}
            for key_column in key_columns:
                if key_column.id not in existing_ids:
                    table_to_columns_map[table_id].append(key_column)

        table_infos: list[TableInfoState] = []
        for table_id, columns in table_to_columns_map.items():
            table = await meta_mysql_repository.get_table_info_by_id(table_id)
            if table is None:
                continue
            table_infos.append(
                TableInfoState(
                    name=table.name,
                    role=table.role,
                    description=table.description,
                    columns=[
                        ColumnInfoState(
                            name=column.name,
                            type=column.type,
                            role=column.role,
                            examples=column.examples,
                            description=column.description,
                            alias=column.alias,
                        )
                        for column in columns
                    ],
                )
            )

        metric_infos: list[MetricInfoState] = [
            MetricInfoState(
                name=metric_info.name,
                description=metric_info.description,
                relevant_columns=metric_info.relevant_columns,
                alias=metric_info.alias,
            )
            for metric_info in retrieved_metrics
        ]

        emit_progress(
            writer,
            "合并召回信息",
            "success",
            f"候选表：{preview_list([table_info['name'] for table_info in table_infos])}\n"
            f"候选指标：{preview_list([metric_info['name'] for metric_info in metric_infos])}",
        )
        logger.info(
            f"合并召回信息完成: tables={[table_info['name'] for table_info in table_infos]}, "
            f"metrics={[metric_info['name'] for metric_info in metric_infos]}"
        )
        return {"table_infos": table_infos, "metric_infos": metric_infos}
    except Exception as exc:
        emit_progress(writer, "合并召回信息", "error", f"召回结果合并失败：{exc}")
        raise
