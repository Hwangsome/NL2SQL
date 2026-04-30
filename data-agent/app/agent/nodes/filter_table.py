import yaml
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.lcel_debug import ainvoke_structured_chain_with_retry
from app.agent.progress import emit_progress, preview_list
from app.agent.state import DataAgentState
from app.agent.structured_output import TableSelectionOutput
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


async def filter_table(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """
    从候选表/字段集合中筛出当前问题真正需要的那部分。

    输入：
    - state["query"]: 用户自然语言问题。
    - state.get("table_infos", []): `merge_retrieved_info` 产出的候选表和字段。
    - runtime.stream_writer: 进度事件输出。

    输出：
    - {"table_infos": list[TableInfoState]}:
      只保留被 LLM 选中的表，以及表内被选中的字段。

    说明：
    - 这个节点不是“重新召回”，而是对候选集合做精筛。
    - prompt 期望返回 `{"tables": {表名: [字段名, ...]}}` 这样的对象，代码会据此裁剪表结构。

    示例：
    - 上游 `table_infos` 可能包含：
      - `fact_order(amount, order_id, product_id, region_id, date_id)`
      - `dim_product(category_name, product_id, brand_name)`
      - `dim_region(region_name, region_id)`
      - `dim_date(date_id, year, month)`
    - 用户问题：`去年华东地区销售额最高的品类是什么`
    - LLM 过滤后可能返回：
      - `{"tables": {"fact_order": ["amount", "product_id", "region_id", "date_id"], "dim_product": ["category_name", "product_id"], "dim_region": ["region_name", "region_id"], "dim_date": ["date_id", "year"]}}`
    - 代码会据此裁剪成更小的 `table_infos`，给 SQL 生成节点使用。

    业务意义：
    - `merge_retrieved_info` 的输出偏“宁可多给一点”；
    - 这里再做一次问题相关性筛选，减少 prompt 噪声和误 join 风险。

    过滤逻辑（实现层）：
    1) 先让 LLM 返回一个“白名单映射”：
       - `tables[表名] = 该表允许保留的字段名数组`
    2) 代码按这个映射做两层裁剪：
       - 表级裁剪：不在 `tables` key 里的表直接丢弃
       - 列级裁剪：保留表内字段名在白名单中的列
    3) 裁剪后的 `table_infos` 会覆盖原候选集写回 state。

    为什么这样能提准：
    - SQL 生成阶段看到的上下文越“相关且精简”，越不容易误选列或多余 join；
    - 通过“表白名单 + 字段白名单”双重过滤，比只过滤字段更稳定。
    """
    writer = runtime.stream_writer
    emit_progress(writer, "过滤表格", "running", "正在筛选本次查询真正需要用到的表和字段。")

    query = state["query"]
    table_infos = state.get("table_infos", [])

    try:
        # 第 1 步：把候选表和字段交给 LLM，让它输出“表->字段白名单”。
        #
        # 例子：
        # - 候选里可能既有 `brand_name` 又有 `category_name`
        # - 问题问的是“品类”，那 `brand_name` 很可能被排掉
        #
        # 这里不是让模型直接返回最终 SQL，而是先返回一个“结构化筛选决策”，
        # 这样可以把“筛选”与“生成 SQL”拆开，便于：
        # - 单独观察筛选质量；
        # - 通过 schema 强约束输出格式；
        # - 在输出漂移时做结构化重试修复。
        prompt = PromptTemplate(template=load_prompt("filter_table_info"), input_variables=["query", "table_infos"])
        result = await ainvoke_structured_chain_with_retry(
            "filter_table",
            prompt,
            TableSelectionOutput,
            {"query": query, "table_infos": yaml.dump(table_infos, allow_unicode=True, sort_keys=False)},
        )

        # `selected_tables` 结构：
        # {
        #   "fact_order": ["amount", "region_id", "date_id"],
        #   "dim_region": ["region_id", "region_name"]
        # }
        #
        # key = 要保留的表名；value = 该表要保留的字段名数组。
        # 后续所有过滤都严格按这个结构执行，不会引入额外表或字段。
        selected_tables = result.tables
        filtered = []
        for table_info in table_infos:
            # 第 2 步（表级过滤）：若表名不在模型返回白名单中，整张表丢弃。
            #
            # 例子：
            # - 候选表里有 `dim_customer`
            # - 但 selected_tables 没有 `dim_customer`
            # - 则整张 `dim_customer` 不进入下游上下文
            if table_info["name"] not in selected_tables:
                continue
            selected_columns = set(selected_tables[table_info["name"]])
            # 第 2 步：只保留被模型点名的字段。
            #
            # 例子：
            # - 原始 `dim_product.columns = [category_name, brand_name, product_id]`
            # - 模型选择 `["category_name", "product_id"]`
            # - 裁剪后只保留这两列
            #
            # 实现细节：
            # - `selected_columns` 使用 set，是为了 O(1) 判断字段是否保留；
            # - 未被选中的字段不会透传到 `generate_sql`，从源头减少“误用列”概率。
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
            # 第 3 步：把结果整理成紧凑摘要，便于前端展示和日志排查。
            #
            # 这里仅做展示层摘要，不改变筛选结果本身。
            table_detail.append(f"{table['name']}({preview_list([column['name'] for column in table['columns']], 8)})")
        emit_progress(writer, "过滤表格", "success", f"保留表和字段：{preview_list(table_detail, 5)}")
        logger.info(f"过滤表格完成: {[table['name'] for table in table_infos]}")
        return {"table_infos": table_infos}
    except Exception as exc:
        emit_progress(writer, "过滤表格", "error", f"表筛选失败：{exc}")
        raise
