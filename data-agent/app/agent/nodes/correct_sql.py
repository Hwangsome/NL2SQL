import re

import yaml
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.lcel_debug import build_debuggable_llm_chain
from app.agent.progress import emit_progress
from app.agent.state import DataAgentState
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


SQL_FENCE_PATTERN = re.compile(r"```(?:sql)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)


def _normalize_sql(text: str) -> str:
    """
    从 LLM 输出中提取纯 SQL，兼容 markdown fenced code block。

    示例：
    - 输入：
      ```sql
      ```sql
      SELECT 1;
      ```
      ```
    - 输出：
      `SELECT 1;`
    """
    match = SQL_FENCE_PATTERN.search(text)
    sql = match.group(1) if match else text
    return sql.strip()


async def correct_sql(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """
    根据 SQL 校验/执行阶段返回的错误信息修正 SQL。

    输入：
    - state["query"]: 原始自然语言问题。
    - state["sql"]: 当前待修正的 SQL。
    - state.get("error", ""): 上游校验或执行返回的错误信息。
    - state.get("table_infos", []): 已筛选的表和字段上下文。
    - state.get("metric_infos", []): 已筛选的指标上下文。
    - state.get("date_info", {}): 日期上下文。
    - state.get("db_info", {}): 数据库方言信息。
    - runtime.stream_writer: 进度事件输出。

    输出：
    - {"sql": str}: 修正后的 SQL 文本。

    说明：
    - 该节点只负责“修正 SQL”，不负责再次校验，校验仍由 `validate_sql` / 执行阶段承担。
    - prompt 中会同时给出原始问题、上下文和数据库报错，帮助模型定位具体修复点。

    示例：
    - 原 SQL：
      - `SELECT fo.sales_amount FROM fact_order fo`
    - 数据库报错：
      - `Unknown column 'fo.sales_amount'`
    - 结合上下文后，模型可能修正为：
      - `SELECT fo.amount FROM fact_order fo`
    - 最终输出：
      - `{"sql": "SELECT fo.amount FROM fact_order fo"}`

    业务意义：
    - 这一步不是重新从零生成 SQL，而是“带着错误信息定点修复”；
    - 通常比完全重写 SQL 更稳定，也更便于排查。
    """
    writer = runtime.stream_writer
    emit_progress(
        writer,
        "校正SQL",
        "running",
        f"正在根据数据库报错修正 SQL。\n原始报错：{state.get('error', '无')}",
    )

    try:
        # 第 1 步：把原始问题、当前 SQL、筛选后的上下文和数据库报错一起交给 LLM。
        #
        # 例子：
        # - query: `去年华东地区销售额最高的品类是什么`
        # - sql: 当前失败 SQL
        # - error: `Unknown column 'fo.sales_amount'`
        #
        # 这种输入方式比“重新生成一条 SQL”更容易让模型定位具体错误。
        prompt = PromptTemplate(
            template=load_prompt("correct_sql"),
            input_variables=["query", "table_infos", "metric_infos", "date_info", "db_info", "sql", "error"],
        )
        chain = build_debuggable_llm_chain("correct_sql", prompt, StrOutputParser())
        result = await chain.ainvoke(
            {
                "query": state["query"],
                "table_infos": yaml.dump(state.get("table_infos", []), allow_unicode=True, sort_keys=False),
                "metric_infos": yaml.dump(state.get("metric_infos", []), allow_unicode=True, sort_keys=False),
                "date_info": yaml.dump(state.get("date_info", {}), allow_unicode=True, sort_keys=False),
                "db_info": yaml.dump(state.get("db_info", {}), allow_unicode=True, sort_keys=False),
                "sql": state["sql"],
                "error": state.get("error", ""),
            }
        )

        # 第 2 步：清洗修正结果，只保留纯 SQL。
        sql = _normalize_sql(result)
        emit_progress(writer, "校正SQL", "success", f"修正后的 SQL：\n{sql}")
        logger.info(f"SQL 校正完成: {sql}")
        return {"sql": sql}
    except Exception as exc:
        emit_progress(writer, "校正SQL", "error", f"SQL 校正失败：{exc}")
        raise
