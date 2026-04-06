import yaml
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.progress import emit_progress, preview_list
from app.agent.state import DataAgentState
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


async def filter_table(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    writer = runtime.stream_writer
    emit_progress(writer, "过滤表格", "running", "正在筛选本次查询真正需要用到的表和字段。")

    query = state["query"]
    table_infos = state.get("table_infos", [])

    try:
        prompt = PromptTemplate(template=load_prompt("filter_table_info"), input_variables=["query", "table_infos"])
        chain = prompt | llm | JsonOutputParser()
        result = await chain.ainvoke(
            {"query": query, "table_infos": yaml.dump(table_infos, allow_unicode=True, sort_keys=False)}
        )

        if isinstance(result, dict):
            filtered = []
            for table_info in table_infos:
                if table_info["name"] not in result:
                    continue
                selected_columns = set(result[table_info["name"]])
                filtered.append(
                    {
                        **table_info,
                        "columns": [
                            column for column in table_info["columns"] if column["name"] in selected_columns
                        ],
                    }
                )
            table_infos = filtered

        table_detail = []
        for table in table_infos:
            table_detail.append(f"{table['name']}({preview_list([column['name'] for column in table['columns']], 8)})")
        emit_progress(writer, "过滤表格", "success", f"保留表和字段：{preview_list(table_detail, 5)}")
        logger.info(f"过滤表格完成: {[table['name'] for table in table_infos]}")
        return {"table_infos": table_infos}
    except Exception as exc:
        emit_progress(writer, "过滤表格", "error", f"表筛选失败：{exc}")
        raise
