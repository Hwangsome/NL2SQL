from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.progress import emit_progress, preview_list
from app.agent.state import DataAgentState
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


async def recall_metric(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    writer = runtime.stream_writer
    emit_progress(writer, "召回指标", "running", "正在扩展关键词并从指标向量库中召回候选指标。")

    query = state["query"]
    embedding_client = runtime.context["embedding_client"]
    metric_qdrant_repository = runtime.context["metric_qdrant_repository"]
    keywords = state.get("keywords", [])

    try:
        prompt = PromptTemplate(
            template=load_prompt("extend_keywords_for_metric_recall"),
            input_variables=["query"],
        )
        chain = prompt | llm | JsonOutputParser()
        result = await chain.ainvoke({"query": query})

        if isinstance(result, dict):
            result = result.get("keywords", [])
        if not isinstance(result, list):
            result = []

        keywords = list(set(keywords + [str(item) for item in result if str(item).strip()]))
        logger.info(f"召回指标扩展关键词: {keywords}")

        metrics_map = {}
        for keyword in keywords:
            query_vector = await embedding_client.aembed_query(keyword)
            metrics = await metric_qdrant_repository.search(query_vector)
            for metric in metrics:
                metrics_map[metric.id] = metric

        retrieved_metrics = list(metrics_map.values())
        emit_progress(
            writer,
            "召回指标",
            "success",
            f"扩展关键词：{preview_list(keywords)}\n召回指标：{preview_list(metrics_map.keys())}",
        )
        logger.info(f"召回指标完成: {list(metrics_map.keys())}")
        return {"retrieved_metrics": retrieved_metrics}
    except Exception as exc:
        emit_progress(writer, "召回指标", "error", f"指标召回失败：{exc}")
        raise
