from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.progress import emit_progress, preview_list
from app.agent.state import DataAgentState
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


async def recall_column(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    writer = runtime.stream_writer
    emit_progress(writer, "召回字段", "running", "正在扩展关键词并从字段向量库中召回候选字段。")

    query = state["query"]
    embedding_client = runtime.context["embedding_client"]
    column_qdrant_repository = runtime.context["column_qdrant_repository"]
    keywords = state.get("keywords", [])

    try:
        prompt = PromptTemplate(
            template=load_prompt("extend_keywords_for_column_recall"),
            input_variables=["query"],
        )
        chain = prompt | llm | JsonOutputParser()
        result = await chain.ainvoke({"query": query})

        if isinstance(result, dict):
            result = result.get("keywords", [])
        if not isinstance(result, list):
            result = []

        keywords = list(set(keywords + [str(item) for item in result if str(item).strip()]))
        logger.info(f"召回字段扩展关键词: {keywords}")

        columns_map = {}
        for keyword in keywords:
            query_vector = await embedding_client.aembed_query(keyword)
            columns = await column_qdrant_repository.search(query_vector)
            for column in columns:
                columns_map[column.id] = column

        retrieved_columns = list(columns_map.values())
        emit_progress(
            writer,
            "召回字段",
            "success",
            f"扩展关键词：{preview_list(keywords)}\n召回字段：{preview_list(columns_map.keys())}",
        )
        logger.info(f"召回字段完成: {list(columns_map.keys())}")
        return {"retrieved_columns": retrieved_columns}
    except Exception as exc:
        emit_progress(writer, "召回字段", "error", f"字段召回失败：{exc}")
        raise
