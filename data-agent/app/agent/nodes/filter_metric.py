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


async def filter_metric(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    writer = runtime.stream_writer
    emit_progress(writer, "过滤指标", "running", "正在筛选本次问题真正相关的指标。")

    query = state["query"]
    metric_infos = state.get("metric_infos", [])

    try:
        prompt = PromptTemplate(template=load_prompt("filter_metric_info"), input_variables=["query", "metric_infos"])
        chain = prompt | llm | JsonOutputParser()
        result = await chain.ainvoke(
            {"query": query, "metric_infos": yaml.dump(metric_infos, allow_unicode=True, sort_keys=False)}
        )

        if isinstance(result, list):
            allowed = set(result)
            metric_infos = [metric_info for metric_info in metric_infos if metric_info["name"] in allowed]

        emit_progress(
            writer,
            "过滤指标",
            "success",
            f"保留指标：{preview_list([metric['name'] for metric in metric_infos])}",
        )
        logger.info(f"过滤指标完成: {[metric['name'] for metric in metric_infos]}")
        return {"metric_infos": metric_infos}
    except Exception as exc:
        emit_progress(writer, "过滤指标", "error", f"指标筛选失败：{exc}")
        raise
