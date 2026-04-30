from datetime import datetime

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.progress import emit_progress
from app.agent.state import DataAgentState, DateInfoState
from app.core.log import logger


async def add_extra_context(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """
    补充当前日期和数据库方言信息，为时间解析和 SQL 生成提供上下文。

    输入：
    - runtime.context["dw_mysql_repository"]: 数仓仓库，用于读取数据库信息。
    - runtime.stream_writer: 进度事件输出。

    输出：
    - {"date_info": DateInfoState, "db_info": DBInfoState}:
      `date_info` 用于解释“今年/去年/本月/本季度”等相对时间；
      `db_info` 用于约束 SQL 生成时遵循对应数据库方言。

    说明：
    - 该节点不依赖用户 query 中的具体字段，只负责补全环境信息。
    - 返回结果会被 `generate_sql`、`correct_sql`、`summarize_answer` 复用。

    示例：
    - 当前系统日期假设是：`2026-04-13`
    - 则会生成：
      - `date_info.date = "2026-04-13"`
      - `date_info.year = 2026`
      - `date_info.last_year = 2025`
      - `date_info.current_quarter = "Q2"`
    - 如果数据库是 MySQL 8，则还会补：
      - `db_info = {"dialect": "mysql", "version": "8.0.x"}`

    为什么需要这一步：
    - 用户问“去年”“本月”“本季度”时，模型不能自己随便猜；
    - 不同数据库方言函数不同，生成 SQL 时也需要明确告诉模型当前是 MySQL 还是别的库。
    """
    writer = runtime.stream_writer
    emit_progress(writer, "添加额外上下文信息", "running", "正在补充当前日期和数据库方言信息。")

    dw_mysql_repository = runtime.context["dw_mysql_repository"]

    try:
        today = datetime.today()
        # 第 1 步：把当前日期拆成 prompt 更容易消费的结构化字段。
        #
        # 例子：
        # - 今天是 2026-04-13
        # - 会得到：
        #   date=2026-04-13
        #   year=2026
        #   last_year=2025
        #   month=4
        #   current_quarter=Q2
        #
        # 这样后面的 `generate_sql` 在处理“去年/本月/本季度”时就不用自行换算。
        date_info = DateInfoState(
            date=today.strftime("%Y-%m-%d"),
            weekday=today.strftime("%A"),
            quarter=f"Q{(today.month - 1) // 3 + 1}",
            year=today.year,
            month=today.month,
            last_year=today.year - 1,
            current_quarter=f"Q{(today.month - 1) // 3 + 1}",
        )

        # 第 2 步：读取数据库方言和版本。
        #
        # 例子：
        # - dialect=mysql
        # - version=8.0.36
        #
        # 这样后面生成 SQL 时，模型知道该用 MySQL 语法，而不是 PostgreSQL/SQLite 语法。
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
