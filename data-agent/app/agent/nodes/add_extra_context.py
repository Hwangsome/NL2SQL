from datetime import datetime

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.progress import emit_progress
from app.agent.state import DataAgentState, DateInfoState
from app.core.log import logger


async def add_extra_context(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    writer = runtime.stream_writer
    emit_progress(writer, "添加额外上下文信息", "running", "正在补充当前日期和数据库方言信息。")

    dw_mysql_repository = runtime.context["dw_mysql_repository"]

    try:
        today = datetime.today()
        date_info = DateInfoState(
            date=today.strftime("%Y-%m-%d"),
            weekday=today.strftime("%A"),
            quarter=f"Q{(today.month - 1) // 3 + 1}",
            year=today.year,
            month=today.month,
            last_year=today.year - 1,
            current_quarter=f"Q{(today.month - 1) // 3 + 1}",
        )
        db_info = await dw_mysql_repository.get_db_info()

        emit_progress(
            writer,
            "添加额外上下文信息",
            "success",
            f"当前日期：{date_info['date']}，今年={date_info['year']}，去年={date_info['last_year']}，本季度={date_info['current_quarter']}。\n"
            f"数据库：{db_info['dialect']} {db_info['version']}",
        )
        logger.info(f"添加额外上下文完成: {date_info}, {db_info}")
        return {"date_info": date_info, "db_info": db_info}
    except Exception as exc:
        emit_progress(writer, "添加额外上下文信息", "error", f"补充上下文失败：{exc}")
        raise
