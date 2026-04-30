from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.lcel_debug import ainvoke_structured_chain_with_retry
from app.agent.progress import emit_progress, preview_list
from app.agent.state import DataAgentState
from app.agent.structured_output import KeywordExpansionOutput
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


async def recall_column(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """
    基于 query 和初始关键词召回候选字段。

    输入：
    - state["query"]: 用户自然语言问题。
    - state.get("keywords", []): 上游 `extract_keywords` 产出的初始关键词。
    - runtime.context["embedding_client"]: 文本向量化客户端。
    - runtime.context["column_qdrant_repository"]: 字段向量检索仓库。
    - runtime.stream_writer: 进度事件输出。

    输出：
    - {"retrieved_columns": list[ColumnInfo]}:
      去重后的字段候选列表，供后续合并和筛选使用。

    说明：
    - 先用 LLM 扩展一轮适合字段召回的关键词。
    - 再对每个关键词生成 embedding，到 Qdrant 中做相似度检索。
    - 最终按字段 id 去重，避免同一个字段被多个关键词重复召回。

    示例：
    - 用户问题：`去年华东地区销售额最高的品类是什么`
    - 上游 `keywords` 可能是：
      - `["华东地区", "销售额", "品类", "最高", "去年华东地区销售额最高的品类是什么"]`
    - LLM 扩展后可能补出：
      - `["地区", "区域", "品类", "类目", "销售金额"]`
    - 合并后的检索词可能类似：
      - `["华东地区", "销售额", "品类", "最高", "地区", "区域", "类目", "销售金额", ...]`
    - 这些词分别做向量检索后，可能召回：
      - `dim_region.region_name`
      - `dim_product.category_name`
      - `fact_order.amount`
      - `dim_date.year`
    - 最终输出：
      - `{"retrieved_columns": [ColumnInfo(...), ...]}`

    为什么需要这一层：
    - 用户说的是业务语言，库里存的是字段名；
    - “品类”不一定叫 `category_name`，“销售额”也不一定直接叫 `sales_amount`；
    - 所以要先扩词，再做语义召回。
    """
    writer = runtime.stream_writer
    emit_progress(writer, "召回字段", "running", "正在扩展关键词并从字段向量库中召回候选字段。")

    query = state["query"]
    embedding_client = runtime.context["embedding_client"]
    column_qdrant_repository = runtime.context["column_qdrant_repository"]
    keywords = state.get("keywords", [])

    try:
        # 第 1 步：让 LLM 把原始 query 扩展成更像“字段名/字段别名”的关键词。
        #
        # 例子：
        # - 输入问题：`去年华东地区销售额最高的品类是什么`
        # - 模型可能扩出：`地区`、`区域`、`品类`、`类目`、`销售金额`
        #
        # 这样做是因为用户语言和元数据字段名未必完全一致。
        prompt = PromptTemplate(
            template=load_prompt("extend_keywords_for_column_recall"),
            input_variables=["query"],
        )
        # 这里统一走“结构化输出 + schema 校验 + 必要时重试”入口。
        #
        # 如果第一次解析失败，这个 helper 不只是简单重试同一请求，还会把：
        # - 原始 prompt
        # - 模型原始输出
        # - 解析错误
        # - 目标 schema
        # 一起回灌给模型做一次纠错重试。
        result = await ainvoke_structured_chain_with_retry(
            "recall_column",
            prompt,
            KeywordExpansionOutput,
            {"query": query},
        )

        # 这里的 `result` 已经是结构化输出对象，不再需要手写 dict/list 兼容逻辑。
        # 如果模型没有按 schema 输出，会在 `with_structured_output` 链路里直接暴露解析失败。
        result = result.keywords

        # 第 2 步：合并“规则抽取关键词”和“LLM 扩展关键词”。
        #
        # 例子：
        # - 上游关键词：["华东地区", "销售额", "品类"]
        # - LLM 扩展：["地区", "区域", "类目", "销售金额"]
        # - 合并后：["华东地区", "销售额", "品类", "地区", "区域", "类目", "销售金额"]
        #
        # 这一步的目标是同时保留：
        # - 原始业务表达
        # - 更贴近库内字段命名的表达
        keywords = list(set(keywords + [str(item) for item in result if str(item).strip()]))
        logger.info(f"召回字段扩展关键词: {keywords}")

        columns_map = {}
        for keyword in keywords:
            # 第 3 步：逐个关键词做向量检索。
            #
            # 例子：
            # - `品类` 可能命中 `dim_product.category_name`
            # - `销售金额` 可能命中 `fact_order.amount`
            # - `地区` 可能命中 `dim_region.region_name`
            #
            # 多个词可能反复命中同一个字段，所以最后统一按字段 id 去重。
            # 先把当前关键词转成 embedding 向量。
            #
            # 这里得到的不是给人看的文本，而是一组浮点数。它的作用是把
            # “销售额”“品类”“地区”这类自然语言表达转成可以做“语义相似度计算”
            # 的数值表示。后续 Qdrant 会拿这个向量去和库里已经提前写入的
            # 字段向量做比对，从而找到语义最接近的字段。
            #
            # 例子：
            # - 关键词：`销售额`
            # - 输出：`[0.12, -0.38, 0.77, ...]`
            #
            # 之所以不直接做字符串精确匹配，是因为用户说“销售额”，库里的
            # 字段可能实际叫 `order_amount`，两者字面上不同，但语义上接近。
            # 为每个关键词记录 embedding 生成过程，便于排查“某个词召回效果差”的问题。
            logger.info(f"召回字段 embedding 开始: keyword={keyword}")
            query_vector = await embedding_client.aembed_query(keyword)
            logger.info(
                f"召回字段 embedding 完成: keyword={keyword}, vector_dim={len(query_vector) if query_vector else 0}"
            )

            # 再用这个查询向量去 Qdrant 的 `column_info` 集合里做相似度检索。
            #
            # 这里检索的对象不是原始数据库字段，而是“字段元信息的向量表示”。
            # 这些向量在构建知识库时就已经提前写入 Qdrant 了，因此运行时只需要
            # 用当前关键词向量去搜索最相近的候选字段即可。
            #
            # 典型结果例如：
            # - `销售额` -> `fact_order.order_amount`
            # - `品类` -> `dim_product.category_name`
            # - `地区` -> `dim_region.region_name`
            #
            # 返回值 `columns` 是一个候选字段列表，而不是单个字段，因为语义召回
            # 本身是“找相近候选”，真正是否使用还要交给后面的过滤与 SQL 生成步骤。
            columns = await column_qdrant_repository.search(query_vector)
            logger.info(f"召回字段检索结果: keyword={keyword}, hit_count={len(columns)}")
            for column in columns:
                # 以字段 id 为 key 写入 map，目的是去重。
                #
                # 因为不同关键词可能会命中同一个字段，例如：
                # - `销售额`
                # - `销售金额`
                # - `GMV`
                #
                # 这几个词都可能召回 `fact_order.order_amount`。如果不去重，
                # 下游看到的候选字段会有大量重复项，既影响日志可读性，也会干扰
                # 后续的表过滤、指标过滤和 SQL 生成。
                columns_map[column.id] = column

        # 第 4 步：把 map 转回列表，供下游 `merge_retrieved_info` 继续整合。
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
