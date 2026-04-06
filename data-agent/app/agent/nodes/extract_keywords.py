import jieba.analyse
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.progress import emit_progress, preview_list
from app.agent.state import DataAgentState
from app.core.log import logger


async def extract_keywords(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    writer = runtime.stream_writer
    emit_progress(writer, "抽取关键字", "running", "正在从用户问题里提取检索关键词。")

    query = state["query"]
    allow_pos = ("n", "nr", "ns", "nt", "nz", "v", "vn", "a", "an", "eng", "i", "l")
    keywords = list(set(jieba.analyse.extract_tags(query, allowPOS=allow_pos) + [query]))

    emit_progress(writer, "抽取关键字", "success", f"提取到的关键词：{preview_list(keywords)}")
    logger.info(f"抽取关键字完成: {keywords}")
    return {"keywords": keywords}
