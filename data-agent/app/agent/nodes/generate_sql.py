import re

import yaml
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.lcel_debug import build_debuggable_llm_chain
from app.agent.progress import emit_progress, preview_text
from app.agent.state import DataAgentState
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


SQL_FENCE_PATTERN = re.compile(r"```(?:sql)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)


def _normalize_sql(text: str) -> str:
    """
    去掉 LLM 可能返回的 ```sql fenced code block，只保留纯 SQL 文本。

    示例：
    - 输入：
      ```sql
      ```sql
      SELECT * FROM fact_order;
      ```
      ```
    - 输出：
      `SELECT * FROM fact_order;`
    """
    match = SQL_FENCE_PATTERN.search(text)
    sql = match.group(1) if match else text
    return sql.strip()


def _resolve_relative_time_query(query: str, date_info: dict) -> str:
    """
    将 query 中的相对时间补充为明确提示，减少 LLM 在时间换算上的歧义。

    输入：
    - query: 用户原始问题。
    - date_info: `add_extra_context` 产出的日期信息。

    输出：
    - str: 原 query，或者追加了“时间解析”提示的新 query。

    示例：
    - 输入：
      - query = `去年华东地区销售额最高的品类是什么`
      - date_info = {"year": 2026, "last_year": 2025, "current_quarter": "Q2", "month": 4}
    - 输出：
      - `去年华东地区销售额最高的品类是什么`
        `时间解析：去年=2025年。生成 SQL 时必须使用以上解析后的具体时间值。`
    """
    current_year = date_info.get("year")
    last_year = date_info.get("last_year")
    current_quarter = date_info.get("current_quarter")
    month = date_info.get("month")

    hints: list[str] = []
    if "今年" in query and current_year is not None:
        hints.append(f"今年={current_year}年")
    if "去年" in query and last_year is not None:
        hints.append(f"去年={last_year}年")
    if "本季度" in query and current_quarter is not None:
        hints.append(f"本季度={current_year}年{current_quarter}")
    if "本月" in query and current_year is not None and month is not None:
        hints.append(f"本月={current_year}年{month}月")

    if not hints:
        return query

    return f"{query}\n时间解析：{'；'.join(hints)}。生成 SQL 时必须使用以上解析后的具体时间值。"


async def generate_sql(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """
    根据筛选后的表、指标和补充上下文生成 SQL。

    输入：
    - state["query"]: 用户自然语言问题。
    - state.get("table_infos", []): 已筛选好的候选表和字段。
    - state.get("metric_infos", []): 已筛选好的候选指标。
    - state.get("date_info", {}): 当前日期上下文。
    - state.get("db_info", {}): 数据库方言与版本信息。
    - runtime.stream_writer: 进度事件输出。

    输出：
    - {"sql": str}: 归一化后的 SQL 文本。

    说明：
    - 该节点是从业务语义到 SQL 的核心转换点。
    - 相对时间会先在 query 文本中展开，再送给 prompt，降低“去年/本季度”等词的歧义。

    示例：
    - 用户问题：`去年华东地区销售额最高的品类是什么`
    - 输入的 `table_infos` 可能已经被筛到只剩：
      - `fact_order(amount, product_id, region_id, date_id)`
      - `dim_product(category_name, product_id)`
      - `dim_region(region_name, region_id)`
      - `dim_date(date_id, year)`
    - 输入的 `metric_infos` 可能只剩：
      - `销售额`
    - 输入的 `date_info` 里会告诉模型：
      - `去年 = 2025`
    - 模型生成后，输出可能是：
      - `SELECT dp.category_name, SUM(fo.amount) AS sales_amount ...`

    业务意义：
    - 这个节点把前面所有“召回、筛选、时间补充”的结果真正收束成一条可执行 SQL；
    - 也是整个链路里最依赖上下文质量的节点。
    """
    writer = runtime.stream_writer
    query = state["query"]
    table_infos = state.get("table_infos", [])
    metric_infos = state.get("metric_infos", [])
    date_info = state.get("date_info", {})
    db_info = state.get("db_info", {})
    # 第 1 步：在进入 prompt 前，把相对时间展开成具体提示。
    #
    # 例子：
    # - 原始 query：`去年华东地区销售额最高的品类是什么`
    # - 展开后会带上：`去年=2025年`
    #
    # 这样可以减少模型把“去年”错解成当前自然年之外的值。
    resolved_query = _resolve_relative_time_query(query, date_info)
    emit_progress(writer, "生成SQL", "running", f"正在根据筛选后的表、指标和时间上下文生成 SQL。\n问题解析：{preview_text(resolved_query)}")

    try:
        # 第 2 步：把候选表、候选指标、日期信息、数据库方言一起交给 LLM 生成 SQL。
        #
        # 这里输入的不是 ORM 对象，而是 YAML 文本；
        # 目的是让模型直接看到稳定、清晰的结构化上下文。
        prompt = PromptTemplate(
            template=load_prompt("generate_sql"),
            input_variables=["query", "table_infos", "metric_infos", "date_info", "db_info"],
        )
        chain = build_debuggable_llm_chain("generate_sql", prompt, StrOutputParser())
        result = await chain.ainvoke(
            {
                "query": resolved_query,
                "table_infos": yaml.dump(table_infos, allow_unicode=True, sort_keys=False),
                "metric_infos": yaml.dump(metric_infos, allow_unicode=True, sort_keys=False),
                "date_info": yaml.dump(date_info, allow_unicode=True, sort_keys=False),
                "db_info": yaml.dump(db_info, allow_unicode=True, sort_keys=False),
            }
        )

        # 第 3 步：清洗模型输出，收敛成纯 SQL。
        #
        # 例子：
        # - 模型可能返回 markdown 代码块；
        # - `_normalize_sql` 会去掉 ```sql 包装，只留下真正执行的 SQL 文本。
        sql = _normalize_sql(result)
        emit_progress(writer, "生成SQL", "success", f"生成的 SQL：\n{sql}")
        logger.info(f"生成SQL完成: {sql}")
        return {"sql": sql}
    except Exception as exc:
        emit_progress(writer, "生成SQL", "error", f"SQL 生成失败：{exc}")
        raise
