# merge_retrieved_info 节点业务总览（基于当前实现）
#
# 核心职责：
# - 将三路召回结果（字段、字段值、指标）做融合、去重、补全与结构化，
#   产出下游 SQL 生成可直接消费的 table_infos / metric_infos。
#
# 7 个步骤：
# 1) 字段去重收敛
#    - 输入 retrieved_columns，按 column_id 去重为 retrieved_columns_map。
#
# 2) 根据指标补齐字段
#    - 遍历 retrieved_metrics.relevant_columns；
#    - 缺失字段从 Meta 库补齐，避免“有指标无落地字段”。
#
# 3) 根据字段值补字段并回填 examples
#    - 遍历 retrieved_values（value -> column_id）；
#    - 缺失字段补齐，并将 value 回填到字段 examples，增强值-字段对应关系。
#
# 4) 按表归组字段
#    - 将 retrieved_columns_map 按 table_id 转为 table_to_columns_map。
#
# 5) 补齐关键连接字段（主键/外键）
#    - 对候选表补 key columns，确保后续 SQL 具备稳定 JOIN 能力。
#
# 6) 组装 table_infos
#    - 将表和字段整理为 prompt 友好结构（name/role/description/columns）。
#
# 7) 组装 metric_infos
#    - 将指标整理为 prompt 友好结构（name/description/relevant_columns/alias）。
#
# 设计要点：
# - 延迟补全：先广召回，再按需补关键字段，减少无效噪声。
# - 双向收敛：值可反推字段并增强 examples，帮助 LLM 理解过滤条件。
# - 可执行性优先：关键连接键补全是 SQL 可执行成功率的重要保障。
#
import json
from dataclasses import asdict, is_dataclass

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.progress import emit_progress, preview_list
from app.agent.state import ColumnInfoState, DataAgentState, MetricInfoState, TableInfoState
from app.core.log import logger
from app.entities.column_info import ColumnInfo
from app.entities.table_info import TableInfo

"""



"""
async def merge_retrieved_info(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """
    将字段、字段值、指标三路召回结果整理成后续 SQL 生成可直接消费的结构化上下文。

    输入：
    - state.get("retrieved_columns", []): 字段召回结果。
    - state.get("retrieved_values", []): 字段取值召回结果。
    - state.get("retrieved_metrics", []): 指标召回结果。
    - runtime.context["meta_mysql_repository"]: 元数据仓库，用于补齐字段和表信息。
    - runtime.stream_writer: 进度事件输出。

    输出：
    - {"table_infos": list[TableInfoState], "metric_infos": list[MetricInfoState]}:
      这是后续 `filter_table`、`filter_metric`、`generate_sql` 的核心输入。

    业务背景：
    - 上游的三路召回来源不同，粒度也不同：
      1. `retrieved_columns` 直接给出“字段”；
      2. `retrieved_values` 给出“某个字段可能出现的值”；
      3. `retrieved_metrics` 给出“业务指标”，但指标往往依赖多个底层字段。
    - SQL 生成节点并不能直接消费这三堆零散结果，它更需要：
      1. 这次查询可能会用到哪些表；
      2. 这些表里哪些字段值得关注；
      3. 这些字段有哪些典型值；
      4. 这次问题提到了哪些业务指标。
    - 因此这个节点的真实职责不是“简单拼接结果”，而是把零散召回结果补齐、归并、去重，
      最终整理成一个适合 LLM 读懂和生成 SQL 的最小上下文。

    示例：
    - 用户问题：`去年华东地区销售额最高的品类是什么`
    - 上游可能召回到：
      - `retrieved_columns`:
        - `fact_order.amount`
        - `dim_product.category_name`
      - `retrieved_values`:
        - `dim_region.region_name = 华东`
      - `retrieved_metrics`:
        - `销售额(relevant_columns=[fact_order.amount, fact_order.order_id, dim_date.date])`
    - 这个节点处理后，期望给下游一份更完整的上下文：
      - 候选表：
        - `fact_order(amount, order_id, product_id, date_id, region_id, ...)`
        - `dim_product(category_name, product_id, ...)`
        - `dim_region(region_name, region_id, ...)`
        - `dim_date(date, year, ...)`
      - 候选指标：
        - `销售额`
    - 这样后面的 SQL 生成节点才更有机会写出类似：
      - `fact_order` 关联 `dim_product`、`dim_region`、`dim_date`
      - 按 `category_name` 分组
      - 过滤 `region_name = '华东'`
      - 过滤去年
      - 聚合 `amount`

    说明：
    - 指标命中的 relevant_columns 会反向补齐到字段集合中，避免只召回到指标却缺少落地字段。
    - 字段值命中的 value 会附加到对应字段的 examples 中，帮助 LLM 理解取值范围。
    - 每张表还会补齐主键/外键等关键连接字段，降低后续生成 SQL 时无法 join 的风险。
    """
    writer = runtime.stream_writer
    emit_progress(writer, "合并召回信息", "running", "正在合并字段、字段值和指标召回结果。")

    retrieved_columns = state.get("retrieved_columns", [])
    retrieved_values = state.get("retrieved_values", [])
    retrieved_metrics = state.get("retrieved_metrics", [])
    """
{
    "retrieved_columns": [
        {
            "id": "dim_region.region_name",
            "name": "region_name",
            "type": "varchar",
            "role": "dimension",
            "examples": [
                "华北",
                "华东",
                "华南"
            ],
            "description": "订单所属的大区名称，如华东、华南等。",
            "alias": [
                "地区",
                "区域",
                "大区"
            ],
            "table_id": "dim_region"
        },
        {
            "id": "dim_region.region_id",
            "name": "region_id",
            "type": "int",
            "role": "primary_key",
            "examples": [
                1,
                2,
                3
            ],
            "description": "地区唯一标识。",
            "alias": [
                "地区ID",
                "区域ID"
            ],
            "table_id": "dim_region"
        },
        {
            "id": "fact_order.region_id",
            "name": "region_id",
            "type": "int",
            "role": "foreign_key",
            "examples": [
                1,
                2,
                3
            ],
            "description": "关联地区维度的外键。",
            "alias": [
                "地区ID",
                "区域ID"
            ],
            "table_id": "fact_order"
        },
        {
            "id": "dim_region.province",
            "name": "province",
            "type": "varchar",
            "role": "dimension",
            "examples": [
                "北京",
                "上海",
                "广东"
            ],
            "description": "订单所属的省份名称。",
            "alias": [
                "省份",
                "省",
                "所在省份"
            ],
            "table_id": "dim_region"
        },
        {
            "id": "dim_product.category",
            "name": "category",
            "type": "varchar",
            "role": "dimension",
            "examples": [
                "笔记本",
                "手机",
                "电视"
            ],
            "description": "商品所属品类。",
            "alias": [
                "商品类别",
                "品类",
                "分类"
            ],
            "table_id": "dim_product"
        },
        {
            "id": "fact_order.order_amount",
            "name": "order_amount",
            "type": "decimal",
            "role": "measure",
            "examples": [
                8999,
                5999,
                6998
            ],
            "description": "订单金额。",
            "alias": [
                "销售额",
                "订单金额",
                "收入"
            ],
            "table_id": "fact_order"
        },
        {
            "id": "fact_order.order_quantity",
            "name": "order_quantity",
            "type": "int",
            "role": "measure",
            "examples": [
                1,
                2,
                3
            ],
            "description": "订单中商品的购买数量。",
            "alias": [
                "销量",
                "购买数量",
                "件数"
            ],
            "table_id": "fact_order"
        }
    ],
    "retrieved_values": [
        {
            "id": "dim_region.region_name.华东",
            "value": "华东",
            "column_id": "dim_region.region_name"
        },
        {
            "id": "dim_region.province.广东",
            "value": "广东",
            "column_id": "dim_region.province"
        },
        {
            "id": "dim_region.region_name.华北",
            "value": "华北",
            "column_id": "dim_region.region_name"
        },
        {
            "id": "dim_region.region_name.华南",
            "value": "华南",
            "column_id": "dim_region.region_name"
        },
        {
            "id": "dim_product.brand.华为",
            "value": "华为",
            "column_id": "dim_product.brand"
        },
        {
            "id": "dim_customer.member_level.黄金",
            "value": "黄金",
            "column_id": "dim_customer.member_level"
        }
    ],
    "retrieved_metrics": [
        {
            "id": "GMV",
            "name": "GMV",
            "description": "全称Gross Merchandise Value，表示所有订单的成交金额总和。",
            "relevant_columns": [
                "fact_order.order_amount"
            ],
            "alias": [
                "成交总额",
                "订单总额"
            ]
        },
        {
            "id": "AOV",
            "name": "AOV",
            "description": "全称Average Order Value，表示平均每笔订单的成交金额。",
            "relevant_columns": [
                "fact_order.order_amount",
                "fact_order.order_quantity"
            ],
            "alias": [
                "客单价",
                "平均订单金额"
            ]
        }
    ]
}

    """
    logger.info(
        "合并召回信息输入(JSON): "
        + json.dumps(
            {
                "retrieved_columns": retrieved_columns,
                "retrieved_values": retrieved_values,
                "retrieved_metrics": retrieved_metrics,
            },
            ensure_ascii=False,
            default=lambda obj: (
                asdict(obj)
                if is_dataclass(obj)
                else (obj.__dict__ if hasattr(obj, "__dict__") else str(obj))
            ),
        )
    )
    meta_mysql_repository = runtime.context["meta_mysql_repository"]

    def _to_jsonable(value: object):
        """把节点内对象转成可 JSON 序列化结构。"""
        if is_dataclass(value):
            return asdict(value)
        if isinstance(value, dict):
            return {str(k): _to_jsonable(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_to_jsonable(item) for item in value]
        if hasattr(value, "__dict__"):
            return {k: _to_jsonable(v) for k, v in value.__dict__.items()}
        return value

    def _log_step_json(step: int, desc: str, payload: dict):
        logger.info(
            "合并召回信息步骤(JSON): "
            + json.dumps(
                {
                    "step": step,
                    "desc": desc,
                    "payload": _to_jsonable(payload),
                },
                ensure_ascii=False,
            )
        )

    try:
        # 第 1 步：先把“字段召回结果”按字段 id 收敛成 map。
        #
        # 这么做有两个目的：
        # 1. 去重：同一个字段可能被多个关键词重复召回；
        # 2. 方便后续增量补齐：后面如果发现指标依赖字段、值命中字段缺失，可以直接塞回这个 map。
        #
        # 到这里为止，map 里只有“直接召回到的字段”。
        #
        # 例子：
        # - retrieved_columns = [fact_order.amount, dim_product.category_name, fact_order.amount]
        # - 收敛后 retrieved_columns_map 只保留两项：
        #   {
        #     "fact_order.amount": ColumnInfo(...),
        #     "dim_product.category_name": ColumnInfo(...),
        #   }
        retrieved_columns_map: dict[str, ColumnInfo] = {
            retrieved_column.id: retrieved_column for retrieved_column in retrieved_columns
        }
        _log_step_json(
            1,
            "字段去重收敛",
            {
                "retrieved_columns_map": retrieved_columns_map,
                "retrieved_columns_map_count": len(retrieved_columns_map),
                "retrieved_columns_map_ids": list(retrieved_columns_map.keys()),
            },
        )

        # 第 2 步：根据指标补齐字段。
        #
        # 业务上，“销售额”“客单价”这类指标往往是用户真正关心的东西，但 SQL 生成不能只知道指标名，
        # 还必须知道这个指标落到哪些底层字段上。例如：
        # - 销售额 -> 可能依赖 amount / quantity / price
        # - 客单价 -> 可能依赖 order_amount / order_cnt
        #
        # 所以上游如果只召回到了指标，没有召回到它依赖的字段，这里需要反向把字段补齐进来。
        # 否则后面的 `generate_sql` 看到了指标，却不知道该去哪张表、用哪些列做聚合或计算。
        #
        # 例子：
        # - retrieved_metrics 里有：
        #   销售额(relevant_columns=["fact_order.amount", "fact_order.order_id", "dim_date.date"])
        # - 但 retrieved_columns_map 里目前只有：
        #   fact_order.amount, dim_product.category_name
        # - 补齐后会新增：
        #   fact_order.order_id, dim_date.date
        #
        # 这样模型看到“销售额”时，不只知道 amount，还知道它和订单、日期字段有关。
        for retrieved_metric in retrieved_metrics:
            for relevant_column in retrieved_metric.relevant_columns:
                if relevant_column not in retrieved_columns_map:
                    column_info = await meta_mysql_repository.get_column_info_by_id(relevant_column)
                    if column_info is not None:
                        retrieved_columns_map[relevant_column] = column_info
        _log_step_json(
            2,
            "根据指标补齐字段",
            {
                "retrieved_columns_map": retrieved_columns_map,
                "retrieved_metrics_count": len(retrieved_metrics),
                "retrieved_columns_map_count_after_metric_patch": len(retrieved_columns_map),
                "retrieved_columns_map_ids_after_metric_patch": list(retrieved_columns_map.keys()),
            },
        )

        # 第 3 步：根据字段值召回补齐字段，并把命中的值挂到字段 examples 上。
        #
        # 这里有两层业务含义：
        # 1. 如果用户问题里出现了“华东”“黄金会员”“手机”这类值，值召回通常能反推出对应字段，
        #    比如 region_name / member_level / category_name。此时即使字段本身没被直接召回，也应补进来。
        # 2. 仅仅知道字段名还不够，LLM 看到字段的典型取值后，才能更稳地判断：
        #    - “华东”更像 region_name 的值，而不是 customer_name；
        #    - “黄金会员”更像 member_level 的值。
        #
        # 所以这里会把命中的 value 塞回字段的 examples，让后面的 prompt 同时看到“字段定义”和“典型值”。
        #
        # 例子：
        # - retrieved_values 里命中：
        #   ValueInfo(value="华东", column_id="dim_region.region_name")
        # - 如果 `dim_region.region_name` 之前不在 retrieved_columns_map 中，会先把这个字段补进来；
        # - 然后把 `"华东"` 追加到该字段的 examples 中。
        #
        # 合并后字段信息可能变成：
        # - dim_region.region_name:
        #   {
        #     name="region_name",
        #     examples=["华北", "华南", "华东"]
        #   }
        #
        # 这样后面的 LLM 更容易理解“华东”应该落在地区字段上。
        for retrieved_value in retrieved_values:
            column_id = retrieved_value.column_id
            column_value = retrieved_value.value
            if column_id not in retrieved_columns_map:
                column_info = await meta_mysql_repository.get_column_info_by_id(column_id)
                if column_info is not None:
                    retrieved_columns_map[column_id] = column_info
            if column_id in retrieved_columns_map and column_value not in retrieved_columns_map[column_id].examples:
                retrieved_columns_map[column_id].examples.append(column_value)
        _log_step_json(
            3,
            "根据字段值补字段并回填 examples",
            {
                "retrieved_columns_map": retrieved_columns_map,
                "retrieved_values_count": len(retrieved_values),
                "retrieved_columns_map_count_after_value_patch": len(retrieved_columns_map),
                "retrieved_columns_map_ids_after_value_patch": list(retrieved_columns_map.keys()),
            },
        )

        # 第 4 步：把字段按所属表归组。
        #
        # SQL 生成阶段真正需要的不是“字段散列表”，而是“表 -> 字段列表”的层级结构。
        # 因为后续 prompt 要回答的是：
        # - 有哪些候选表？
        # - 每张表有哪些可用字段？
        # - 哪几张表之间可能需要 join？
        #
        # 例子：
        # - 当前字段 map 中有：
        #   fact_order.amount
        #   fact_order.order_id
        #   dim_product.category_name
        #   dim_region.region_name
        # - 归组后会变成：
        #   {
        #     "fact_order": [amount, order_id],
        #     "dim_product": [category_name],
        #     "dim_region": [region_name],
        #   }
        table_to_columns_map: dict[str, list[ColumnInfo]] = {}
        for column in retrieved_columns_map.values():
            table_to_columns_map.setdefault(column.table_id, []).append(column)
        _log_step_json(
            4,
            "按表归组字段",
            {
                "retrieved_columns_map": retrieved_columns_map,
                "table_count": len(table_to_columns_map),
                "table_to_columns": {
                    table_id: [column.id for column in columns] for table_id, columns in table_to_columns_map.items()
                },
            },
        )

        # 第 5 步：为每张候选表补齐关键连接字段。
        #
        # 这是这个节点里最容易被忽视，但对 SQL 成功率最关键的步骤之一。
        #
        # 为什么要补 key columns：
        # - 上游召回更容易命中“业务字段”，例如地区名、品牌名、销售额、订单量；
        # - 但 SQL 真正写出来时，往往还需要主键/外键/维度连接键才能完成 join；
        # - 如果 prompt 里只有业务字段，没有连接键，模型经常会：
        #   1. 凭空猜 join 条件；
        #   2. 漏 join；
        #   3. 生成无法执行或语义错误的 SQL。
        #
        # 所以这里会把每张候选表的关键字段一并补上，哪怕这些字段不是用户问题直接提到的。
        # 这属于“为了 SQL 可生成性补上下文”，而不是“为了业务解释补上下文”。
        #
        # 例子：
        # - `fact_order` 当前只有：
        #   [amount, order_id]
        # - 但这张表和维表关联通常还需要：
        #   [product_id, region_id, date_id]
        # - `get_key_columns_by_table_id("fact_order")` 返回这些关键列后，
        #   最终 `fact_order` 会被补成：
        #   [amount, order_id, product_id, region_id, date_id]
        #
        # 这样模型后面才能更自然地生成：
        # - `fact_order.product_id = dim_product.product_id`
        # - `fact_order.region_id = dim_region.region_id`
        # - `fact_order.date_id = dim_date.date_id`
        for table_id in list(table_to_columns_map.keys()):
            key_columns = await meta_mysql_repository.get_key_columns_by_table_id(table_id)
            existing_ids = {column.id for column in table_to_columns_map[table_id]}
            for key_column in key_columns:
                if key_column.id not in existing_ids:
                    table_to_columns_map[table_id].append(key_column)
        _log_step_json(
            5,
            "补齐关键连接字段",
            {
                "table_to_columns_map": table_to_columns_map,
                "table_to_columns_after_key_patch": {
                    table_id: [column.id for column in columns] for table_id, columns in table_to_columns_map.items()
                }
            },
        )

        # 第 6 步：将“表实体 + 字段实体”整理成 prompt 更容易消费的 dict 结构。
        #
        # 这里没有直接把 ORM/实体对象往下传，而是转成 `TableInfoState / ColumnInfoState`，
        # 原因是后面的节点会把这些对象序列化成 YAML/JSON 发给 LLM。
        # 用简单 dict 结构可以减少序列化歧义，也避免把不相关的运行时字段泄露给 prompt。
        #
        # 例子：
        # - ORM/实体对象里可能有内部 id、table_id 等机器字段；
        # - 这里会整理成更适合 prompt 的结构：
        #   {
        #     "name": "dim_region",
        #     "role": "维度表",
        #     "description": "地区维度",
        #     "columns": [
        #       {
        #         "name": "region_name",
        #         "type": "varchar",
        #         "examples": ["华东", "华北"]
        #       }
        #     ]
        #   }
        table_infos: list[TableInfoState] = []
        for table_id, columns in table_to_columns_map.items():
            table = await meta_mysql_repository.get_table_info_by_id(table_id)
            if table is None:
                continue
            # 每条 table_info 都描述一张候选表，以及这张表上当前“值得让 LLM 看见”的字段集合。
            #
            # 注意：这里保留的是候选字段，不代表这些字段最终一定会进入 SQL。
            # 后面 `filter_table` 还会再做一轮问题相关性筛选，把上下文进一步压缩。
            table_infos.append(
                TableInfoState(
                    name=table.name,
                    role=table.role,
                    description=table.description,
                    columns=[
                        ColumnInfoState(
                            name=column.name,
                            type=column.type,
                            role=column.role,
                            examples=column.examples,
                            description=column.description,
                            alias=column.alias,
                        )
                        for column in columns
                    ],
                )
            )
        _log_step_json(
            6,
            "组装 table_infos",
            {
                "table_to_columns_map": table_to_columns_map,
                "table_infos_count": len(table_infos),
                "table_info_names": [
                    table_info.get("name", "") if isinstance(table_info, dict) else getattr(table_info, "name", "")
                    for table_info in table_infos
                ],
            },
        )

        # 第 7 步：将指标实体压平成 prompt 友好的结构。
        #
        # 和 table_infos 类似，这里保留指标名、描述、别名、依赖字段，
        # 供 `filter_metric` 和 `generate_sql` 使用。
        #
        # 为什么 relevant_columns 还要继续保留：
        # - 一方面前面已经据此补过字段；
        # - 另一方面后面的 LLM 仍然可能需要看到“这个指标和哪些字段相关”，
        #   这样它在生成聚合表达式时更稳。
        #
        # 例子：
        # - metric_infos 中的一项可能是：
        #   {
        #     "name": "销售额",
        #     "description": "订单实付金额汇总",
        #     "relevant_columns": ["fact_order.amount", "fact_order.order_id"],
        #     "alias": ["成交金额", "GMV"]
        #   }
        #
        # 后面的 `filter_metric` 会判断这次问题是否真的要用“销售额”，
        # `generate_sql` 则会结合 relevant_columns 理解该怎么聚合。
        metric_infos: list[MetricInfoState] = [
            MetricInfoState(
                name=metric_info.name,
                description=metric_info.description,
                relevant_columns=metric_info.relevant_columns,
                alias=metric_info.alias,
            )
            for metric_info in retrieved_metrics
        ]
        _log_step_json(
            7,
            "组装 metric_infos",
            {
                "metric_infos_count": len(metric_infos),
                "metric_info_names": [
                    metric_info.get("name", "")
                    if isinstance(metric_info, dict)
                    else getattr(metric_info, "name", "")
                    for metric_info in metric_infos
                ],
                "metric_infos": metric_infos,
            },
        )

        # 到这里，三路召回结果已经被整理成两份核心上下文：
        # - table_infos: 候选表 + 候选字段 + 字段示例值
        # - metric_infos: 候选指标
        #
        # 后续链路会继续做两件事：
        # 1. `filter_table` / `filter_metric` 再缩小范围，去掉误召回项；
        # 2. `generate_sql` 基于这份上下文生成真正可执行的 SQL。
        #
        # 例子：
        # - 当前输出：
        #   table_infos = [fact_order(...), dim_product(...), dim_region(...), dim_date(...)]
        #   metric_infos = [销售额]
        # - `filter_table` 之后可能进一步收敛为：
        #   fact_order(amount, product_id, region_id, date_id)
        #   dim_product(category_name, product_id)
        #   dim_region(region_name, region_id)
        #   dim_date(date_id, year)
        # - 最终 `generate_sql` 就更容易稳定生成目标 SQL。
        emit_progress(
            writer,
            "合并召回信息",
            "success",
            f"候选表：{preview_list([table_info['name'] for table_info in table_infos])}\n"
            f"候选指标：{preview_list([metric_info['name'] for metric_info in metric_infos])}",
        )
        logger.info(
            f"合并召回信息完成: tables={[table_info['name'] for table_info in table_infos]}, "
            f"metrics={[metric_info['name'] for metric_info in metric_infos]}"
        )
        logger.info(
            "合并召回信息输出(JSON): "
            + json.dumps(
                {"table_infos": table_infos, "metric_infos": metric_infos},
                ensure_ascii=False,
            )
        )
        """
{
    "table_infos": [
        {
            "name": "fact_order",
            "role": "fact",
            "description": "订单事实表，记录订单数量和金额等核心指标。",
            "columns": [
                {
                    "name": "order_amount",
                    "type": "decimal",
                    "role": "measure",
                    "examples": [
                        8999,
                        5999,
                        6998
                    ],
                    "description": "订单金额。",
                    "alias": [
                        "销售额",
                        "订单金额",
                        "收入"
                    ]
                },
                {
                    "name": "order_quantity",
                    "type": "int",
                    "role": "measure",
                    "examples": [
                        1,
                        2,
                        3
                    ],
                    "description": "订单中商品的购买数量。",
                    "alias": [
                        "销量",
                        "购买数量",
                        "件数"
                    ]
                },
                {
                    "name": "region_id",
                    "type": "int",
                    "role": "foreign_key",
                    "examples": [
                        1,
                        2,
                        3
                    ],
                    "description": "关联地区维度的外键。",
                    "alias": [
                        "地区ID",
                        "区域ID"
                    ]
                },
                {
                    "name": "customer_id",
                    "type": "int",
                    "role": "foreign_key",
                    "examples": [
                        "[",
                        "1",
                        "0",
                        "0",
                        "1",
                        ",",
                        " ",
                        "1",
                        "0",
                        "0",
                        "2",
                        ",",
                        " ",
                        "1",
                        "0",
                        "0",
                        "3",
                        "]"
                    ],
                    "description": "关联客户维度的外键。",
                    "alias": [
                        "[",
                        "\"",
                        "客",
                        "户",
                        "I",
                        "D",
                        "\"",
                        ",",
                        " ",
                        "\"",
                        "用",
                        "户",
                        "I",
                        "D",
                        "\"",
                        "]"
                    ]
                },
                {
                    "name": "date_id",
                    "type": "int",
                    "role": "foreign_key",
                    "examples": [
                        "[",
                        "2",
                        "0",
                        "2",
                        "4",
                        "0",
                        "1",
                        "1",
                        "5",
                        ",",
                        " ",
                        "2",
                        "0",
                        "2",
                        "4",
                        "0",
                        "3",
                        "0",
                        "8",
                        ",",
                        " ",
                        "2",
                        "0",
                        "2",
                        "4",
                        "0",
                        "6",
                        "1",
                        "8",
                        "]"
                    ],
                    "description": "关联时间维度的外键。",
                    "alias": [
                        "[",
                        "\"",
                        "日",
                        "期",
                        "\"",
                        ",",
                        " ",
                        "\"",
                        "下",
                        "单",
                        "日",
                        "期",
                        "\"",
                        "]"
                    ]
                },
                {
                    "name": "order_id",
                    "type": "int",
                    "role": "primary_key",
                    "examples": [
                        "[",
                        "1",
                        ",",
                        " ",
                        "2",
                        ",",
                        " ",
                        "3",
                        "]"
                    ],
                    "description": "订单唯一标识。",
                    "alias": [
                        "[",
                        "\"",
                        "订",
                        "单",
                        "I",
                        "D",
                        "\"",
                        "]"
                    ]
                },
                {
                    "name": "product_id",
                    "type": "int",
                    "role": "foreign_key",
                    "examples": [
                        "[",
                        "2",
                        "0",
                        "0",
                        "1",
                        ",",
                        " ",
                        "2",
                        "0",
                        "0",
                        "2",
                        ",",
                        " ",
                        "2",
                        "0",
                        "0",
                        "3",
                        "]"
                    ],
                    "description": "关联商品维度的外键。",
                    "alias": [
                        "[",
                        "\"",
                        "商",
                        "品",
                        "I",
                        "D",
                        "\"",
                        ",",
                        " ",
                        "\"",
                        "产",
                        "品",
                        "I",
                        "D",
                        "\"",
                        "]"
                    ]
                }
            ]
        },
        {
            "name": "dim_region",
            "role": "dim",
            "description": "地区维度表，用于描述订单发生的地理区域信息。",
            "columns": [
                {
                    "name": "province",
                    "type": "varchar",
                    "role": "dimension",
                    "examples": [
                        "北京",
                        "上海",
                        "广东"
                    ],
                    "description": "订单所属的省份名称。",
                    "alias": [
                        "省份",
                        "省",
                        "所在省份"
                    ]
                },
                {
                    "name": "region_name",
                    "type": "varchar",
                    "role": "dimension",
                    "examples": [
                        "华北",
                        "华东",
                        "华南"
                    ],
                    "description": "订单所属的大区名称，如华东、华南等。",
                    "alias": [
                        "地区",
                        "区域",
                        "大区"
                    ]
                },
                {
                    "name": "region_id",
                    "type": "int",
                    "role": "primary_key",
                    "examples": [
                        1,
                        2,
                        3
                    ],
                    "description": "地区唯一标识。",
                    "alias": [
                        "地区ID",
                        "区域ID"
                    ]
                }
            ]
        },
        {
            "name": "dim_product",
            "role": "dim",
            "description": "商品维度表，描述商品的基本属性信息。",
            "columns": [
                {
                    "name": "category",
                    "type": "varchar",
                    "role": "dimension",
                    "examples": [
                        "笔记本",
                        "手机",
                        "电视"
                    ],
                    "description": "商品所属品类。",
                    "alias": [
                        "商品类别",
                        "品类",
                        "分类"
                    ]
                },
                {
                    "name": "brand",
                    "type": "varchar",
                    "role": "dimension",
                    "examples": [
                        "华为",
                        "苹果",
                        "小米"
                    ],
                    "description": "商品品牌名称。",
                    "alias": [
                        "品牌",
                        "品牌名称"
                    ]
                },
                {
                    "name": "product_id",
                    "type": "int",
                    "role": "primary_key",
                    "examples": [
                        "[",
                        "2",
                        "0",
                        "0",
                        "1",
                        ",",
                        " ",
                        "2",
                        "0",
                        "0",
                        "2",
                        ",",
                        " ",
                        "2",
                        "0",
                        "0",
                        "3",
                        "]"
                    ],
                    "description": "商品唯一标识。",
                    "alias": [
                        "[",
                        "\"",
                        "商",
                        "品",
                        "I",
                        "D",
                        "\"",
                        ",",
                        " ",
                        "\"",
                        "产",
                        "品",
                        "I",
                        "D",
                        "\"",
                        "]"
                    ]
                }
            ]
        }
    ],
    "metric_infos": [
        {
            "name": "GMV",
            "description": "全称Gross Merchandise Value，表示所有订单的成交金额总和。",
            "relevant_columns": [
                "fact_order.order_amount"
            ],
            "alias": [
                "成交总额",
                "订单总额"
            ]
        },
        {
            "name": "AOV",
            "description": "全称Average Order Value，表示平均每笔订单的成交金额。",
            "relevant_columns": [
                "fact_order.order_amount",
                "fact_order.order_quantity"
            ],
            "alias": [
                "客单价",
                "平均订单金额"
            ]
        }
    ]
}
        """
        return {"table_infos": table_infos, "metric_infos": metric_infos}
    except Exception as exc:
        emit_progress(writer, "合并召回信息", "error", f"召回结果合并失败：{exc}")
        raise
