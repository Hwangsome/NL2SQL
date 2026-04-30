from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.lcel_debug import ainvoke_structured_chain_with_retry
from app.agent.progress import emit_progress, preview_list
from app.agent.state import DataAgentState
from app.agent.structured_output import KeywordExpansionOutput
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


async def recall_metric(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """
    基于 query 和初始关键词召回候选指标。

    输入：
    - state["query"]: 用户自然语言问题。
    - state.get("keywords", []): 上游 `extract_keywords` 产出的关键词。
    - runtime.context["embedding_client"]: 文本向量化客户端。
    - runtime.context["metric_qdrant_repository"]: 指标向量检索仓库。
    - runtime.stream_writer: 进度事件输出。

    输出：
    - {"retrieved_metrics": list[MetricInfo]}:
      去重后的指标候选列表，供后续表/指标筛选和 SQL 生成使用。

    说明：
    - 先让 LLM 生成更像“指标名称/指标别名”的扩展词。
    - 再对每个词做向量检索，最终按指标 id 合并。

    示例：
    - 用户问题：`去年华东地区销售额最高的品类是什么`
    - 上游关键词可能是：
      - `["华东地区", "销售额", "品类"]`
    - LLM 可能扩成更像指标名的表达：
      - `["销售金额", "成交金额", "GMV"]`
    - 做完向量召回后，可能命中：
      - `销售额`
      - `订单量`
    - 最终按指标 id 去重，返回：
      - `{"retrieved_metrics": [MetricInfo(name="销售额", ...), ...]}`

    业务意义：
    - 用户常用“销售额”“客单价”“销量”这些业务词提问；
    - 而系统要靠指标元数据才能知道具体该怎么聚合、依赖哪些字段。
    """
    writer = runtime.stream_writer
    emit_progress(writer, "召回指标", "running", "正在扩展关键词并从指标向量库中召回候选指标。")

    query = state["query"]
    embedding_client = runtime.context["embedding_client"]
    metric_qdrant_repository = runtime.context["metric_qdrant_repository"]
    keywords = state.get("keywords", [])

    try:
        # 第 1 步：把 query 扩展成更像“指标口径”的词。
        #
        # 例子：
        # - `销售额` 可能扩成：`销售金额`、`成交金额`、`GMV`
        # - `客单价` 可能扩成：`平均订单金额`
        prompt = PromptTemplate(
            template=load_prompt("extend_keywords_for_metric_recall"),
            input_variables=["query"],
        )
        # 统一把结构化输出失败纳入重试链路，避免节点层重复实现重试逻辑。
        result = await ainvoke_structured_chain_with_retry(
            "recall_metric",
            prompt,
            KeywordExpansionOutput,
            {"query": query},
        )

        result = result.keywords

        # 第 2 步：合并上游关键词与指标扩展词。
        #
        # 例子：
        # - 上游：["销售额", "品类"]
        # - 扩展：["销售金额", "成交金额", "GMV"]
        # - 合并后一起做向量检索，扩大命中面。
        keywords = list(set(keywords + [str(item) for item in result if str(item).strip()]))
        logger.info(f"召回指标扩展关键词: {keywords}")

        metrics_map = {}
        for keyword in keywords:
            # 第 3 步：对每个词做指标向量检索。
            #
            # 例子：
            # - `GMV` 和 `销售金额` 可能都会命中同一个指标“销售额”
            # - 所以这里统一按指标 id 合并，避免重复。
            query_vector = await embedding_client.aembed_query(keyword)
            metrics = await metric_qdrant_repository.search(query_vector)
            for metric in metrics:
                metrics_map[metric.id] = metric

        # 第 4 步：把候选指标交给下游，后续还会再做一次精筛。
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
