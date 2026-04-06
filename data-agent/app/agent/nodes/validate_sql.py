from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.progress import emit_progress, preview_text
from app.agent.state import DataAgentState
from app.core.log import logger


async def validate_sql(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    writer = runtime.stream_writer
    dw_mysql_repository = runtime.context["dw_mysql_repository"]
    sql = state["sql"]
    emit_progress(writer, "验证SQL", "running", f"正在通过 EXPLAIN 校验 SQL 是否可执行。\nSQL 预览：{preview_text(sql)}")

    try:
        await dw_mysql_repository.validate_sql(sql)
        emit_progress(writer, "验证SQL", "success", "SQL 校验通过，可以进入执行阶段。")
        logger.info("SQL 验证通过")
        return {"error": None}
    except Exception as exc:
        emit_progress(writer, "验证SQL", "error", f"SQL 校验失败：{exc}")
        logger.error(f"SQL 验证失败: {exc}")
        return {"error": str(exc)}
