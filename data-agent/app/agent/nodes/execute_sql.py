from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.progress import emit_progress, preview_text
from app.agent.state import DataAgentState
from app.core.log import logger


async def execute_sql(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """
    执行最终 SQL，并将结果集写回状态。

    输入：
    - state["sql"]: 已通过校验、可执行的 SQL。
    - runtime.context["dw_mysql_repository"]: 数仓仓库，负责执行 SQL。
    - runtime.stream_writer: 进度事件输出。

    输出：
    - {"result_rows": list[dict[str, Any]]}: SQL 查询结果。

    说明：
    - 这里只关注执行和回传结果，不做业务总结。
    - 首行结果会被写进 progress detail，方便前端快速预览和调试。

    示例：
    - 输入 SQL：
      - `SELECT dp.category_name, SUM(fo.amount) AS sales_amount ...`
    - 数据库返回：
      - `[{"category_name": "手机", "sales_amount": 128000}, {"category_name": "家电", "sales_amount": 95000}]`
    - 最终输出：
      - `{"result_rows": [...]}`
    - progress 里还会额外带：
      - 总行数
      - 首行样例

    业务意义：
    - 到这里说明 SQL 已经通过校验，链路正式从“理解问题”进入“拿真实数据”阶段；
    - 下游 `summarize_answer` 会基于这里的结果给用户生成业务结论。
    """
    writer = runtime.stream_writer
    emit_progress(writer, "执行SQL", "running", f"正在执行 SQL。\nSQL 预览：{preview_text(state['sql'])}")

    dw_mysql_repository = runtime.context["dw_mysql_repository"]

    try:
        # 第 1 步：真正执行 SQL，取回结果集。
        result = await dw_mysql_repository.execute_sql(state["sql"])
        first_row = result[0] if result else None
        detail = f"返回 {len(result)} 行结果。"
        if first_row is not None:
            # 第 2 步：把首行结果放进进度详情，方便快速确认结果形状是否符合预期。
            #
            # 例子：
            # - 首行样例：{"category_name": "手机", "sales_amount": 128000}
            detail += f"\n首行样例：{first_row}"
        emit_progress(writer, "执行SQL", "success", detail)
        logger.info(f"SQL 执行完成，返回 {len(result)} 行")
        return {"result_rows": result}
    except Exception as exc:
        emit_progress(writer, "执行SQL", "error", f"SQL 执行失败：{exc}")
        raise
