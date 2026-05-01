from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.lcel_debug import ainvoke_structured_chain_with_retry
from app.agent.progress import emit_progress, preview_list
from app.agent.state import DataAgentState
from app.agent.structured_output import KeywordExpansionOutput
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


async def recall_value(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """
    基于 query 和初始关键词召回字段取值候选。

    输入：
    - state["query"]: 用户自然语言问题。
    - state.get("keywords", []): 上游提取出的初始检索词。
    - runtime.context["value_es_repository"]: Elasticsearch 检索仓库。
    - runtime.stream_writer: 进度事件输出。

    输出：
    - {"retrieved_values": list[ValueInfo]}:
      去重后的字段取值候选，后续会被并入字段 examples 中。

    说明：
    - 这里和字段/指标召回不同，不走向量检索，而是直接用关键词到 ES 中查值。
    - 多个关键词命中同一个值时会按 value id 去重。

    示例：
    - 用户问题：`去年华东地区销售额最高的品类是什么`
    - 上游关键词可能有：
      - `["华东地区", "销售额", "品类"]`
    - LLM 面向“字段值”扩展后，可能补出：
      - `["华东", "地区", "区域"]`
    - 然后会拿这些词去 ES 查值，可能命中：
      - `dim_region.region_name = 华东`
      - `dim_region.region_name = 华北`
      - `dim_product.category_name = 手机`
    - 最终返回的是值对象列表，而不是字段列表。

    真实运行样例（对应日志）：
    - 问题：`统计去年各地区的销售总额`
    - 扩展关键词（示例）：
      - `全国`、`地区`、`省份`、`大区`、`年份`、`统计` 等
    - ES 命中的值（示例）：
      - `dim_region.country.中国`
    - 这些值会在 `merge_retrieved_info` 阶段反向补充到对应字段的 examples 中，
      帮助后续 SQL 生成理解“用户可能在筛哪些取值”。

    业务意义：
    - 字段召回负责找到“可能相关的列”；
    - 值召回负责告诉系统“用户这次说的华东/黄金会员/手机，可能是哪个列上的值”。
    """
    writer = runtime.stream_writer
    emit_progress(writer, "召回字段取值", "running", "正在扩展关键词并从 Elasticsearch 中检索字段取值。")

    query = state["query"]
    value_es_repository = runtime.context["value_es_repository"]
    keywords = state.get("keywords", [])

    try:
        # 第 1 步：借助 LLM 扩展更像“字段值”的查询词。
        #
        # 例子：
        # - 原问题：`去年华东地区销售额最高的品类是什么`
        # - 模型可能补出：`华东`、`地区`、`区域`
        #
        # 这样更容易在 ES 中命中实际存储的枚举值或文本值。
        prompt = PromptTemplate(
            template=load_prompt("extend_keywords_for_value_recall"),
            input_variables=["query"],
        )
        # 统一走结构化输出重试入口，覆盖解析失败和瞬时调用异常。
        result = await ainvoke_structured_chain_with_retry(
            "recall_value",
            prompt,
            KeywordExpansionOutput,
            {"query": query},
        )

        result = result.keywords

        # 第 2 步：合并上游关键词和面向值检索的扩展词。
        #
        # 例子：
        # - 上游：["华东地区", "销售额", "品类"]
        # - LLM：["华东", "地区", "区域"]
        # - 合并后：["华东地区", "销售额", "品类", "华东", "地区", "区域"]
        #
        # 在“统计去年各地区的销售总额”样例里，这里会出现“全国/大区/省份”等词，
        # 用于提高地区类值在 ES 中的命中概率。
        keywords = list(set(keywords + [str(item) for item in result if str(item).strip()]))
        logger.info(f"召回字段取值扩展关键词: {keywords}")

        values_map = {}
        for keyword in keywords:
            # 第 3 步：逐个关键词查询 ES。
            #
            # 例子：
            # - 关键词 `华东` 可能命中 `dim_region.region_name = 华东`
            # - 关键词 `品类` 可能命中一些类目名相关值
            #
            # 这里按 value id 去重，避免同一个值被多个词重复命中。
            # 对应本次真实日志，`dim_region.country.中国` 就是这一步命中的一个值样例。
            #    {
            #   "id": "dim_region.region_name.华东",
            #    "value": "华东",
            #   "column_id": "dim_region.region_name"
          #   }
            # 
            values = await value_es_repository.search(keyword)
            for value in values:
                values_map[value.id] = value

        # 第 4 步：把命中的值列表交给 `merge_retrieved_info`，
        # 让它反向补字段并写入 examples。
        retrieved_values = list(values_map.values())
        logger.info(f"召回字段取值对象列表: {[value.id for value in retrieved_values]}")
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
