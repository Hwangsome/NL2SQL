import re

import yaml
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.progress import emit_progress
from app.agent.state import DataAgentState
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


SQL_FENCE_PATTERN = re.compile(r"```(?:sql)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)


def _normalize_sql(text: str) -> str:
    match = SQL_FENCE_PATTERN.search(text)
    sql = match.group(1) if match else text
    return sql.strip()


async def correct_sql(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    writer = runtime.stream_writer
    emit_progress(
        writer,
        "校正SQL",
        "running",
        f"正在根据数据库报错修正 SQL。\n原始报错：{state.get('error', '无')}",
    )

    try:
        prompt = PromptTemplate(
            template=load_prompt("correct_sql"),
            input_variables=["query", "table_infos", "metric_infos", "date_info", "db_info", "sql", "error"],
        )
        chain = prompt | llm | StrOutputParser()
        result = await chain.ainvoke(
            {
                "query": state["query"],
                "table_infos": yaml.dump(state.get("table_infos", []), allow_unicode=True, sort_keys=False),
                "metric_infos": yaml.dump(state.get("metric_infos", []), allow_unicode=True, sort_keys=False),
                "date_info": yaml.dump(state.get("date_info", {}), allow_unicode=True, sort_keys=False),
                "db_info": yaml.dump(state.get("db_info", {}), allow_unicode=True, sort_keys=False),
                "sql": state["sql"],
                "error": state.get("error", ""),
            }
        )
        sql = _normalize_sql(result)
        emit_progress(writer, "校正SQL", "success", f"修正后的 SQL：\n{sql}")
        logger.info(f"SQL 校正完成: {sql}")
        return {"sql": sql}
    except Exception as exc:
        emit_progress(writer, "校正SQL", "error", f"SQL 校正失败：{exc}")
        raise
