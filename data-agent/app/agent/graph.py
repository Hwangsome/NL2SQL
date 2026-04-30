import argparse
import asyncio
import json
from typing import Any

from langgraph.constants import END, START
from langgraph.graph import StateGraph

from app.agent.context import DataAgentContext
from app.agent.nodes.add_extra_context import add_extra_context
from app.agent.nodes.correct_sql import correct_sql
from app.agent.nodes.execute_sql import execute_sql
from app.agent.nodes.extract_keywords import extract_keywords
from app.agent.nodes.filter_metric import filter_metric
from app.agent.nodes.filter_table import filter_table
from app.agent.nodes.generate_sql import generate_sql
from app.agent.nodes.merge_retrieved_info import merge_retrieved_info
from app.agent.nodes.recall_column import recall_column
from app.agent.nodes.recall_metric import recall_metric
from app.agent.nodes.recall_value import recall_value
from app.agent.nodes.summarize_answer import summarize_answer
from app.agent.nodes.validate_sql import validate_sql
from app.agent.state import DataAgentState
from app.clients.embedding_client_manager import embedding_client_manager
from app.clients.es_client_manager import es_client_manager
from app.clients.mysql_client_manager import dw_mysql_client_manager, meta_mysql_client_manager
from app.clients.qdrant_client_manager import qdrant_client_manager
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository

"""
                              +-----------+                               
                              | __start__ |                               
                              +-----------+                               
                                    *                                     
                                    *                                     
                                    *                                     
                          +------------------+                            
                          | extract_keywords |                            
                         *+------------------+**                          
                     ****           *           *****                     
                *****               *                ****                 
             ***                    *                    ***              
+---------------+           +---------------+           +--------------+  
| recall_column |           | recall_metric |           | recall_value |  
+---------------+****       +---------------+        ***+--------------+  
                     ****           *           *****                     
                         *****      *       ****                          
                              ***   *    ***                              
                        +----------------------+                          
                        | merge_retrieved_info |                          
                        +----------------------+                          
                             **            **                             
                           **                **                           
                         **                    **                         
              +---------------+           +--------------+                
              | filter_metric |           | filter_table |                
              +---------------+           +--------------+                
                             **            **                             
                               **        **                               
                                 **    **                                 
                          +-------------------+                           
                          | add_extra_context |                           
                          +-------------------+                           
                                    *                                     
                                    *                                     
                                    *                                     
                            +--------------+                              
                            | generate_sql |                              
                            +--------------+                              
                                    *                                     
                                    *                                     
                                    *                                     
                            +--------------+                              
                            | validate_sql |                              
                            +--------------+                              
                             ..           ...                             
                           ..                ..                           
                         ..                    ..                         
                +-------------+                  ..                       
                | correct_sql |                ..                         
                +-------------+              ..                           
                             **           ...                             
                               **       ..                                
                                 **   ..                                  
                             +-------------+                              
                             | execute_sql |                              
                             +-------------+                              
                                    *                                     
                                    *                                     
                                    *                                     
                          +------------------+                            
                          | summarize_answer |                            
                          +------------------+                            
                                    *                                     
                                    *                                     
                                    *                                     
                               +---------+                                
                               | __end__ |                                
                               +---------+                                

"""
# 这里使用的是 `StateGraph`，不是普通的“函数编排图”。
#
# `state_schema=DataAgentState` 的意义是：
# - 把 `DataAgentState` 里声明的每个字段都注册成图状态的一部分
# - 例如：
#   - `query`
#   - `keywords`
#   - `retrieved_columns`
#   - `sql`
#   - `result_rows`
#
# 在运行时，每个节点都会收到“当前状态”作为入参：
#   async def some_node(state: DataAgentState, runtime: Runtime[...]):
#       ...
#
# 同时，节点返回的 `dict` 会被 LangGraph 解释成“状态更新”而不是普通返回值。
# 例如：
#   return {"keywords": keywords}
#
# 这并不是节点自己去改 `state["keywords"]`，而是 LangGraph 在内部把这个 dict
# 提取成 `(key, value)` 更新项，再写回对应的状态通道。下游节点因此可以直接从
# `state` 里继续读取这些字段。
#
# 可以把它理解成：
# - 节点输入：完整当前 state
# - 节点输出：本节点要追加/覆盖的 state patch
# - LangGraph：负责把 patch merge 回全局 state
graph_builder = StateGraph(state_schema=DataAgentState, context_schema=DataAgentContext)

graph_builder.add_node("extract_keywords", extract_keywords)
graph_builder.add_node("recall_column", recall_column)
graph_builder.add_node("recall_value", recall_value)
graph_builder.add_node("recall_metric", recall_metric)
graph_builder.add_node("merge_retrieved_info", merge_retrieved_info)
graph_builder.add_node("filter_table", filter_table)
graph_builder.add_node("filter_metric", filter_metric)
graph_builder.add_node("add_extra_context", add_extra_context)
graph_builder.add_node("generate_sql", generate_sql)
graph_builder.add_node("validate_sql", validate_sql)
graph_builder.add_node("correct_sql", correct_sql)
graph_builder.add_node("execute_sql", execute_sql)
graph_builder.add_node("summarize_answer", summarize_answer)

graph_builder.add_edge(START, "extract_keywords")
graph_builder.add_edge("extract_keywords", "recall_column")
graph_builder.add_edge("extract_keywords", "recall_value")
graph_builder.add_edge("extract_keywords", "recall_metric")
graph_builder.add_edge("recall_column", "merge_retrieved_info")
graph_builder.add_edge("recall_value", "merge_retrieved_info")
graph_builder.add_edge("recall_metric", "merge_retrieved_info")
graph_builder.add_edge("merge_retrieved_info", "filter_table")
graph_builder.add_edge("merge_retrieved_info", "filter_metric")
graph_builder.add_edge("filter_table", "add_extra_context")
graph_builder.add_edge("filter_metric", "add_extra_context")
graph_builder.add_edge("add_extra_context", "generate_sql")
graph_builder.add_edge("generate_sql", "validate_sql")
graph_builder.add_conditional_edges(
    "validate_sql",
    lambda state: "execute_sql" if state.get("error") is None else "correct_sql",
    {"execute_sql": "execute_sql", "correct_sql": "correct_sql"},
)
graph_builder.add_edge("correct_sql", "execute_sql")
graph_builder.add_edge("execute_sql", "summarize_answer")
graph_builder.add_edge("summarize_answer", END)

# `compile()` 会把上面声明式定义的节点、边和状态 schema 转成真正可执行的运行时图。
#
# 编译后的图内部会做几件关键事情：
# 1. 识别 `DataAgentState` 中有哪些合法状态字段
# 2. 为每个字段建立状态通道（默认语义近似“保存该字段最后一次写入的值”）
# 3. 在节点执行后，把节点 return 的 dict 解释为状态更新
# 4. 把更新合并进当前 state，再传给后续节点
#
# 所以调用：
#   await graph.ainvoke(...)
# 或：
#   async for chunk in graph.astream(...):
#
# 时，节点之间能共享 `keywords`、`retrieved_columns`、`sql` 等字段，
# 本质上靠的就是这层编译后的状态合并机制。
graph = graph_builder.compile()


def _build_arg_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。

    这个 `main` 的目标不是替代 HTTP 接口，而是提供一个本地命令行入口，
    方便开发时单独测试 LangGraph 编排链路是否能从“自然语言问题”一路执行到
    “结论 + SQL + 查询结果”。
    """

    parser = argparse.ArgumentParser(description="直接在命令行里测试 Data Agent 的 LangGraph 流程。")
    parser.add_argument(
        "--query",
        default="统计去年各地区的销售总额",
        help="要测试的自然语言问句。默认使用一个项目内常见的问数问题。",
    )
    parser.add_argument(
        "--show-state",
        action="store_true",
        help="执行结束后打印裁剪后的最终 state，便于调试字段召回、SQL 和结果。",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="调试模式。开启后遇到异常会直接抛出完整堆栈，便于定位代码问题。",
    )
    return parser


def _format_stream_chunk(chunk: dict[str, Any]) -> str:
    """把 LangGraph 自定义流事件格式化为适合命令行阅读的文本。

    图执行过程中会持续产出 `progress`、`answer`、`result`、`error` 等事件。
    这里统一把这些事件转成一行或几行可读文本，方便在终端中观察每一步到底
    做了什么，而不需要手动盯原始 JSON。
    """

    chunk_type = chunk.get("type", "unknown")
    if chunk_type == "progress":
        step = chunk.get("step", "unknown")
        status = chunk.get("status", "unknown")
        detail = chunk.get("detail")
        if detail:
            return f"[progress] {step} | {status}\n{detail}"
        return f"[progress] {step} | {status}"

    if chunk_type == "answer":
        content = chunk.get("content", "")
        return f"[answer] {content}"

    if chunk_type == "result":
        data = chunk.get("data", [])
        return f"[result] rows={len(data)}\n{json.dumps(data, ensure_ascii=False, indent=2, default=str)}"

    if chunk_type == "error":
        return f"[error] {chunk.get('message', '')}"

    return f"[{chunk_type}] {json.dumps(chunk, ensure_ascii=False, default=str)}"


def _trim_state_for_display(state: dict[str, Any]) -> dict[str, Any]:
    """裁剪最终 state，避免命令行输出过长。

    `graph.ainvoke()` 返回的 state 里可能包含较长的召回结果和完整明细表。
    对命令行调试来说，我们更关心关键字段是否产出，因此这里保留摘要信息，
    避免终端一次性刷出几百行内容。
    """

    trimmed = dict(state)

    # 对大列表保留长度和前几项，避免调试输出淹没真正关心的 SQL、answer 和 error。
    for key in ("retrieved_columns", "retrieved_values", "retrieved_metrics", "table_infos", "metric_infos"):
        value = trimmed.get(key)
        if isinstance(value, list):
            trimmed[key] = {"count": len(value), "preview": value[:3]}

    result_rows = trimmed.get("result_rows")
    if isinstance(result_rows, list):
        trimmed["result_rows"] = {"count": len(result_rows), "preview": result_rows[:5]}

    return trimmed


async def _build_runtime_context() -> tuple[DataAgentContext, Any, Any]:
    """初始化命令行测试图所需的运行时依赖。

    这里复用项目正式运行时使用的客户端管理器，而不是造一套独立的测试对象：
    - embedding 客户端：负责关键词向量化
    - Qdrant：负责字段/指标向量召回
    - Elasticsearch：负责字段值召回
    - MySQL(meta/dw)：负责读取元数据和执行最终 SQL

    返回值中除了 `DataAgentContext` 外，还额外返回两个 session，目的是让调用方
    能在整个图执行周期内保持数据库连接有效，并在结束后统一关闭。
    """

    embedding_client_manager.init()
    qdrant_client_manager.init()
    es_client_manager.init()
    meta_mysql_client_manager.init()
    dw_mysql_client_manager.init()

    if meta_mysql_client_manager.session_factory is None:
        raise RuntimeError("Meta MySQL session factory is not initialized.")
    if dw_mysql_client_manager.session_factory is None:
        raise RuntimeError("DW MySQL session factory is not initialized.")
    if qdrant_client_manager.client is None:
        raise RuntimeError("Qdrant client is not initialized.")
    if es_client_manager.client is None:
        raise RuntimeError("Elasticsearch client is not initialized.")
    if embedding_client_manager.client is None:
        raise RuntimeError("Embedding client is not initialized.")

    # 这里显式持有两个数据库 session，是因为 graph 的多个节点都需要复用同一组
    # repository；如果 session 提前离开上下文，后续节点会在运行中途失去数据库连接。
    meta_session = meta_mysql_client_manager.session_factory()
    dw_session = dw_mysql_client_manager.session_factory()

    context = DataAgentContext(
        embedding_client=embedding_client_manager.client,
        column_qdrant_repository=ColumnQdrantRepository(qdrant_client_manager.client),
        value_es_repository=ValueESRepository(es_client_manager.client),
        metric_qdrant_repository=MetricQdrantRepository(qdrant_client_manager.client),
        meta_mysql_repository=MetaMySQLRepository(meta_session),
        dw_mysql_repository=DWMySQLRepository(dw_session),
    )
    return context, meta_session, dw_session


async def _close_runtime_context(meta_session: Any, dw_session: Any) -> None:
    """关闭命令行测试图时临时创建的 session 和客户端。"""

    await meta_session.close()
    await dw_session.close()
    await qdrant_client_manager.close()
    await es_client_manager.close()
    await meta_mysql_client_manager.close()
    await dw_mysql_client_manager.close()
    await embedding_client_manager.close()


async def main() -> None:
    """命令行测试入口。

    使用方式：

    ```bash
    cd /Users/bill/code/AI/NL2SQL/data-agent
    uv run python -m app.agent.graph --query "统计去年各地区的销售总额" --show-state
    ```

    这会真实执行整张 LangGraph：
    - 输出每一步的 progress 事件
    - 输出流式 answer 片段
    - 输出最终 result 事件
    - 可选打印最终 state 摘要
    """

    args = _build_arg_parser().parse_args()
    state = DataAgentState(query=args.query)
    context, meta_session, dw_session = await _build_runtime_context()

    print(f"[graph-test] query={args.query}")

    try:
        # 先用 astream 观察整张图在执行过程中发出的自定义事件。
        # 这一步最适合调试“卡在哪一步”“哪一步召回为空”“SQL 什么时候生成”等问题。
        async for chunk in graph.astream(input=state, context=context, stream_mode="updates",version="v2",subgraphs=True):
            print(_format_stream_chunk(chunk))

        print("[graph-test] graph execution completed.")

        if args.show_state:
            # 只有在明确要求查看最终 state 时，才额外执行一次 `ainvoke`。
            #
            # 原因是 `astream(..., stream_mode="custom")` 的主要目标是观察过程事件，
            # 但它不会直接把完整最终 state 交给命令行。为了拿到完整 state，我们
            # 需要再跑一次图；这会增加一次真实执行成本，因此默认关闭。
            final_state = await graph.ainvoke(input=state, context=context)
            print(json.dumps(_trim_state_for_display(final_state), ensure_ascii=False, indent=2, default=str))
    except Exception as exc:
        # 命令行测试入口默认优先保证“错误可读性”，而不是直接抛出整段框架堆栈。
        #
        # 对日常联调来说，开发者最关心的是：
        # - 是配置错了
        # - 是模型额度不足
        # - 还是某个节点本身逻辑报错
        #
        # 因此默认只输出简洁错误说明；当需要追具体调用栈时，再显式加 `--debug`。
        print(f"[graph-test] failed: {exc.__class__.__name__}: {exc}")
        if args.debug:
            raise
    finally:
        await _close_runtime_context(meta_session, dw_session)


if __name__ == "__main__":
    asyncio.run(main())
