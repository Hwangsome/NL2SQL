from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.progress import emit_progress, preview_text
from app.agent.state import DataAgentState
from app.core.log import logger


async def execute_sql(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    writer = runtime.stream_writer
    emit_progress(writer, "执行SQL", "running", f"正在执行 SQL。\nSQL 预览：{preview_text(state['sql'])}")

    dw_mysql_repository = runtime.context["dw_mysql_repository"]

    try:
        result = await dw_mysql_repository.execute_sql(state["sql"])
        first_row = result[0] if result else None
        detail = f"返回 {len(result)} 行结果。"
        if first_row is not None:
            detail += f"\n首行样例：{first_row}"
        emit_progress(writer, "执行SQL", "success", detail)
        logger.info(f"SQL 执行完成，返回 {len(result)} 行")
        return {"result_rows": result}
    except Exception as exc:
        emit_progress(writer, "执行SQL", "error", f"SQL 执行失败：{exc}")
        raise
