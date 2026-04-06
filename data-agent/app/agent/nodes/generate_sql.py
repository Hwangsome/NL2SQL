import re

import yaml
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.progress import emit_progress, preview_text
from app.agent.state import DataAgentState
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


SQL_FENCE_PATTERN = re.compile(r"```(?:sql)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)


def _normalize_sql(text: str) -> str:
    match = SQL_FENCE_PATTERN.search(text)
    sql = match.group(1) if match else text
    return sql.strip()


def _resolve_relative_time_query(query: str, date_info: dict) -> str:
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
    writer = runtime.stream_writer
    query = state["query"]
    table_infos = state.get("table_infos", [])
    metric_infos = state.get("metric_infos", [])
    date_info = state.get("date_info", {})
    db_info = state.get("db_info", {})
    resolved_query = _resolve_relative_time_query(query, date_info)
    emit_progress(writer, "生成SQL", "running", f"正在根据筛选后的表、指标和时间上下文生成 SQL。\n问题解析：{preview_text(resolved_query)}")

    try:
        prompt = PromptTemplate(
            template=load_prompt("generate_sql"),
            input_variables=["query", "table_infos", "metric_infos", "date_info", "db_info"],
        )
        chain = prompt | llm | StrOutputParser()
        result = await chain.ainvoke(
            {
                "query": resolved_query,
                "table_infos": yaml.dump(table_infos, allow_unicode=True, sort_keys=False),
                "metric_infos": yaml.dump(metric_infos, allow_unicode=True, sort_keys=False),
                "date_info": yaml.dump(date_info, allow_unicode=True, sort_keys=False),
                "db_info": yaml.dump(db_info, allow_unicode=True, sort_keys=False),
            }
        )
        sql = _normalize_sql(result)
        emit_progress(writer, "生成SQL", "success", f"生成的 SQL：\n{sql}")
        logger.info(f"生成SQL完成: {sql}")
        return {"sql": sql}
    except Exception as exc:
        emit_progress(writer, "生成SQL", "error", f"SQL 生成失败：{exc}")
        raise
