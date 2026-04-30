import json

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.lcel_debug import build_debuggable_llm_chain
from app.agent.progress import emit_progress, preview_text
from app.agent.state import DataAgentState
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


def _build_time_note(query: str, date_info: dict | None) -> str:
    """
    根据 query 中的相对时间词，生成一段可直接面向用户展示的时间解释。

    示例：
    - query: `去年华东地区销售额最高的品类是什么`
    - date_info: {"date": "2026-04-13", "last_year": 2025}
    - 输出：
      - `这里的“去年”指 2025 年（相对于当前日期 2026-04-13）`
    """
    if not date_info:
        return ""

    today = date_info.get("date")
    year = date_info.get("year")
    last_year = date_info.get("last_year")
    month = date_info.get("month")
    quarter = date_info.get("current_quarter")
    notes: list[str] = []

    if "去年" in query and last_year is not None and today:
        notes.append(f"这里的“去年”指 {last_year} 年（相对于当前日期 {today}）")
    if "今年" in query and year is not None and today:
        notes.append(f"这里的“今年”指 {year} 年（相对于当前日期 {today}）")
    if "本月" in query and year is not None and month is not None and today:
        notes.append(f"这里的“本月”指 {year} 年 {month} 月（相对于当前日期 {today}）")
    if "本季度" in query and year is not None and quarter is not None and today:
        notes.append(f"这里的“本季度”指 {year} 年 {quarter}（相对于当前日期 {today}）")

    return "；".join(notes)


def _prepend_time_note(answer: str, time_note: str) -> str:
    """
    将时间解释安全地拼接到答案前缀，避免重复添加。

    示例：
    - time_note = `这里的“去年”指 2025 年`
    - answer = `销售额最高的品类是手机`
    - 输出：
      - `这里的“去年”指 2025 年。销售额最高的品类是手机`
    """
    if not time_note:
        return answer
    if time_note in answer:
        return answer
    return f"{time_note}。{answer}"


def _fallback_answer(query: str, result_rows: list[dict], time_note: str = "") -> str:
    """
    当 LLM 总结失败或没有产生有效内容时，按规则生成一个兜底答案。

    输入：
    - query: 用户原始问题。
    - result_rows: SQL 执行结果。
    - time_note: 相对时间解释。

    输出：
    - str: 可直接返回给前端展示的结论文本。

    示例：
    - 如果 `result_rows = []`：
      - 返回“本次查询没有返回数据”
    - 如果 `result_rows` 只有 1 行：
      - 返回“得到 1 条结果，结论是 ...”
    - 如果 `result_rows` 有多行：
      - 返回“返回 N 条记录，从前几条结果看 ...”
    """
    if not result_rows:
        answer = f"针对“{query}”，本次查询没有返回数据。可以调整筛选条件、时间范围或指标口径后重试。"
        return _prepend_time_note(answer, time_note)

    if len(result_rows) == 1:
        row = result_rows[0]
        metrics = [f"{key}={value}" for key, value in row.items()]
        answer = f"针对“{query}”，本次查询得到 1 条结果，结论是：{'，'.join(metrics)}。"
        return _prepend_time_note(answer, time_note)

    preview = []
    for row in result_rows[:3]:
        preview.append("，".join(f"{key}={value}" for key, value in row.items()))
    preview_text = "；".join(preview)
    answer = (
        f"针对“{query}”，本次查询返回 {len(result_rows)} 条记录。"
        f"从前几条结果看，{preview_text}。请结合下方表格查看完整明细。"
    )
    return _prepend_time_note(answer, time_note)


async def summarize_answer(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """
    将 SQL 结果总结成可读结论，并把结果流式返回给前端。

    输入：
    - state["query"]: 用户自然语言问题。
    - state.get("sql", ""): 已执行的 SQL。
    - state.get("result_rows", []): SQL 查询结果。
    - state.get("date_info"): 日期上下文，用于解释相对时间。
    - runtime.stream_writer: 既用于 progress，也用于 answer/result 流式消息。

    输出：
    - {"answer": str}: 最终业务结论文本。

    副作用：
    - 连续写出 `{"type": "answer", "delta": ...}`，把答案逐段流式推给前端。
    - 最后写出 `{"type": "result", ...}`，附带结果集、最终答案和 SQL。

    说明：
    - 优先走 LLM 生成自然语言总结。
    - 如果 LLM 失败或没有返回有效内容，则退回规则模板总结，保证用户始终能看到结果说明。

    示例：
    - 用户问题：`去年华东地区销售额最高的品类是什么`
    - SQL 结果可能是：
      - `[{"category_name": "手机", "sales_amount": 128000}]`
    - 时间说明可能是：
      - `这里的“去年”指 2025 年（相对于当前日期 2026-04-13）`
    - LLM 正常时，最终回答可能是：
      - `这里的“去年”指 2025 年... 华东地区销售额最高的品类是手机，销售额为 128000。`
    - 如果 LLM 失败，fallback 可能返回：
      - `针对“去年华东地区销售额最高的品类是什么”，本次查询得到 1 条结果，结论是：category_name=手机，sales_amount=128000。`

    业务意义：
    - 这一步把数据库结果翻译成业务人员可直接阅读的结论；
    - 同时保留流式体验，让前端能边生成边展示。
    """
    writer = runtime.stream_writer
    emit_progress(writer, "生成结论", "running", "正在根据 SQL 结果生成业务可读结论。")

    result_rows = state.get("result_rows", [])
    date_info = state.get("date_info")
    time_note = _build_time_note(state["query"], date_info)
    answer = ""
    generated_body = ""

    if time_note:
        prefix = f"{time_note}。"
        answer += prefix
        # 第 1 步：如果问题里有“去年/今年/本月/本季度”，先把时间解释单独流给前端。
        #
        # 例子：
        # - `这里的“去年”指 2025 年（相对于当前日期 2026-04-13）`
        writer({"type": "answer", "delta": prefix})
    else:
        prefix = ""

    try:
        # 第 2 步：把 query、SQL、结果集、时间说明交给 LLM，总结成业务语言。
        #
        # 例子：
        # - query：用户原始问题
        # - sql：最终执行 SQL
        # - result_rows：实际查询结果
        # - time_note：相对时间解释
        prompt = PromptTemplate(
            template=load_prompt("summarize_result"),
            input_variables=["query", "sql", "result_rows", "row_count", "date_info", "time_note"],
        )
        chain = build_debuggable_llm_chain("summarize_answer", prompt, StrOutputParser())
        async for chunk in chain.astream(
            {
                "query": state["query"],
                "sql": state.get("sql", ""),
                "result_rows": json.dumps(result_rows, ensure_ascii=False, default=str),
                "row_count": len(result_rows),
                "date_info": json.dumps(date_info, ensure_ascii=False, default=str),
                "time_note": time_note,
            }
        ):
            if not chunk:
                continue
            # 第 3 步：实时透传 LLM 输出，保持前端边生成边展示的体验。
            generated_body += chunk
            answer += chunk
            writer({"type": "answer", "delta": chunk})
    except Exception as exc:
        logger.warning(f"结论生成失败，回退到规则总结: {exc}")

    answer = answer.strip()
    if not generated_body.strip():
        fallback_answer = _fallback_answer(state["query"], result_rows, time_note)
        suffix = fallback_answer[len(prefix) :] if prefix and fallback_answer.startswith(prefix) else fallback_answer
        answer = fallback_answer
        # 第 4 步：如果 LLM 没产出有效内容，回退到规则模板总结。
        #
        # 例子：
        # - 单行结果时，直接把首行 key/value 整理成一句结论
        writer({"type": "answer", "delta": suffix})

    # 第 5 步：发送最终结果包，供前端展示表格、答案和 SQL。
    emit_progress(writer, "生成结论", "success", f"最终结论：{preview_text(answer, 320)}")
    writer(
        {
            "type": "result",
            "data": result_rows,
            "answer": answer,
            "sql": state.get("sql", ""),
        }
    )
    logger.info("结论生成完成")
    return {"answer": answer}
