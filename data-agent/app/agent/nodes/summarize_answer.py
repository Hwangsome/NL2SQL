import json

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.progress import emit_progress, preview_text
from app.agent.state import DataAgentState
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


def _build_time_note(query: str, date_info: dict | None) -> str:
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
    if not time_note:
        return answer
    if time_note in answer:
        return answer
    return f"{time_note}。{answer}"


def _fallback_answer(query: str, result_rows: list[dict], time_note: str = "") -> str:
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
        writer({"type": "answer", "delta": prefix})
    else:
        prefix = ""

    try:
        prompt = PromptTemplate(
            template=load_prompt("summarize_result"),
            input_variables=["query", "sql", "result_rows", "row_count", "date_info", "time_note"],
        )
        chain = prompt | llm | StrOutputParser()
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
        writer({"type": "answer", "delta": suffix})

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
