from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.progress import emit_progress, preview_text
from app.agent.state import DataAgentState
from app.core.log import logger


async def validate_sql(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """
    在正式执行前校验 SQL 是否可执行。

    输入：
    - state["sql"]: `generate_sql` 或 `correct_sql` 产出的 SQL。
    - runtime.context["dw_mysql_repository"]: 数仓仓库，负责通过 EXPLAIN 等方式验证 SQL。
    - runtime.stream_writer: 进度事件输出。

    输出：
    - {"error": None}: SQL 校验通过。
    - {"error": str}: SQL 校验失败，返回具体错误信息，供图中的条件分支决定是否进入 `correct_sql`。

    说明：
    - 这里不抛出校验失败给图中断，而是显式返回 error，让后续可以走 SQL 修正分支。

    示例：
    - 输入 SQL：
      - `SELECT dp.category_name, SUM(fo.amount) ...`
    - 如果 EXPLAIN 成功：
      - 返回 `{"error": None}`
      - 图会继续走到 `execute_sql`
    - 如果 EXPLAIN 失败，例如：
      - `Unknown column 'fo.sales_amount'`
    - 返回：
      - `{"error": "Unknown column 'fo.sales_amount'"}`
      - 图会转去 `correct_sql`

    业务意义：
    - 这一步是 SQL 安全闭环的一部分；
    - 它把“生成是否靠谱”从猜测变成显式校验。
    """
    writer = runtime.stream_writer
    dw_mysql_repository = runtime.context["dw_mysql_repository"]
    sql = state["sql"]
    emit_progress(writer, "验证SQL", "running", f"正在通过 EXPLAIN 校验 SQL 是否可执行。\nSQL 预览：{preview_text(sql)}")

    try:
        # 第 1 步：用数据库侧校验方式验证 SQL。
        #
        # 这里通常不是直接执行全量查询，而是通过 EXPLAIN / 预检查判断语法、表名、字段名、join 是否成立。
        await dw_mysql_repository.validate_sql(sql)
        emit_progress(writer, "验证SQL", "success", "SQL 校验通过，可以进入执行阶段。")
        logger.info("SQL 验证通过")
        return {"error": None}
    except Exception as exc:
        # 第 2 步：把错误信息写回状态，而不是直接中断图。
        #
        # 这样后面的 `correct_sql` 可以拿到原 SQL + 报错信息，继续做自动修正。
        emit_progress(writer, "验证SQL", "error", f"SQL 校验失败：{exc}")
        logger.error(f"SQL 验证失败: {exc}")
        return {"error": str(exc)}
