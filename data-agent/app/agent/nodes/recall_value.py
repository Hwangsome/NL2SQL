from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.progress import emit_progress, preview_list
from app.agent.state import DataAgentState
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


async def recall_value(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    writer = runtime.stream_writer
    emit_progress(writer, "召回字段取值", "running", "正在扩展关键词并从 Elasticsearch 中检索字段取值。")

    query = state["query"]
    value_es_repository = runtime.context["value_es_repository"]
    keywords = state.get("keywords", [])

    try:
        prompt = PromptTemplate(
            template=load_prompt("extend_keywords_for_value_recall"),
            input_variables=["query"],
        )
        chain = prompt | llm | JsonOutputParser()
        result = await chain.ainvoke({"query": query})

        if isinstance(result, dict):
            result = result.get("keywords", [])
        if not isinstance(result, list):
            result = []

        keywords = list(set(keywords + [str(item) for item in result if str(item).strip()]))
        logger.info(f"召回字段取值扩展关键词: {keywords}")

        values_map = {}
        for keyword in keywords:
            values = await value_es_repository.search(keyword)
            for value in values:
                values_map[value.id] = value

        retrieved_values = list(values_map.values())
        emit_progress(
            writer,
            "召回字段取值",
            "success",
            f"扩展关键词：{preview_list(keywords)}\n命中的字段取值：{preview_list(values_map.keys())}",
        )
        logger.info(f"召回字段取值完成: {list(values_map.keys())}")
        return {"retrieved_values": retrieved_values}
    except Exception as exc:
        emit_progress(writer, "召回字段取值", "error", f"字段取值召回失败：{exc}")
        raise
