import json
import os
from typing import Any

from langchain_core.messages import BaseMessage
from langchain_core.output_parsers import BaseOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.prompt_values import PromptValue
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel

from app.agent.llm import llm
from app.core.log import logger


def _is_lcel_debug_enabled() -> bool:
    """判断是否开启 LCEL 调试日志。"""

    return os.getenv("LCEL_DEBUG", "false").strip().lower() in {"1", "true", "yes", "on"}


def _structured_retry_count() -> int:
    """读取结构化输出链路的最大重试次数。

    这里读取环境变量而不是写死常量，目的是让本地调试和线上运行都能按需调整：
    - `0`：失败立即抛错，不做重试
    - `1`：失败后最多再试 1 次
    - `2+`：更激进的容错策略

    默认值取 `1`，原因是：
    - 结构化输出失败通常是偶发格式漂移，重试一次有实际价值；
    - 继续无限重试只会放大延迟，收益很低。
    """

    raw = os.getenv("LCEL_STRUCTURED_RETRY_COUNT", "1").strip()
    try:
        return max(int(raw), 0)
    except ValueError:
        return 1


def _truncate_text(text: str, max_chars: int = 6000) -> str:
    """裁剪调试日志文本，避免一次打印过长上下文。"""

    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}\n... <truncated {len(text) - max_chars} chars>"


def _serialize_lcel_payload(payload: Any) -> str:
    """把 LCEL 流经的数据结构序列化为适合日志查看的文本。

    在 `prompt | llm | parser` 这类 LCEL 链路中，输入输出对象通常不是简单字符串，
    常见类型包括：
    - `PromptValue`：prompt 模板渲染后的最终模型输入
    - `BaseMessage`：聊天模型返回的原始消息对象
    - `dict/list`：节点上下文或 parser 前后的结构化数据

    这里统一把它们转换为可阅读文本，方便直接在日志里定位：
    - prompt 是否按预期渲染
    - 模型原始输出是否符合 parser 预期
    """

    if isinstance(payload, PromptValue):
        return payload.to_string()

    if isinstance(payload, BaseMessage):
        content = payload.content
        if isinstance(content, str):
            return content
        return json.dumps(content, ensure_ascii=False, indent=2, default=str)

    if isinstance(payload, BaseModel):
        return payload.model_dump_json(ensure_ascii=False, indent=2)

    if isinstance(payload, (dict, list, tuple)):
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    return str(payload)


def create_lcel_debug_runnable(step_name: str, direction: str) -> RunnableLambda:
    """创建一个可插入 LCEL 管道的调试 Runnable。

    这个 Runnable 的行为非常简单：
    - 接收上游 Runnable 的输出
    - 如果开启了 `LCEL_DEBUG`，打印一条带步骤名和方向的调试日志
    - 原样返回输入值，不改变链路语义

    因此它非常适合放在：
    - `prompt` 后面：看最终送给模型的内容
    - `llm` 后面：看模型原始输出
    """

    def _debug_tap(payload: Any) -> Any:
        if _is_lcel_debug_enabled():
            text = _truncate_text(_serialize_lcel_payload(payload))
            logger.info(f"[LCEL][{step_name}][{direction}]\n{text}")
        return payload

    return RunnableLambda(_debug_tap)


def build_debuggable_llm_chain(step_name: str, prompt: Any, output_parser: BaseOutputParser) -> Any:
    """构建一个带输入/输出调试能力的标准 LCEL 链。

    最终结构为：
    - prompt
    - input debug runnable
    - llm
    - output debug runnable
    - output parser

    这样做的目标是把调试逻辑从业务节点中抽离出来，避免每个节点都重复写
    一遍“记录 prompt 和模型输出”的样板代码。
    """

    return (
        prompt
        | create_lcel_debug_runnable(step_name, "input")
        | llm
        | create_lcel_debug_runnable(step_name, "output")
        | output_parser
    )


def _unwrap_structured_output(step_name: str, payload: dict[str, Any]) -> Any:
    """从 include_raw=True 的结构化输出结果里提取解析后的对象。

    `with_structured_output(..., include_raw=True)` 返回的数据结构是：
    - `raw`: 模型原始消息
    - `parsed`: 结构化解析后的对象
    - `parsing_error`: 解析异常

    这里统一做两件事：
    - 如果开启调试，打印 `raw/parsed/parsing_error`
    - 如果解析失败，直接抛错，让调用方尽快发现“模型没有遵守 schema”
    """

    if _is_lcel_debug_enabled():
        raw = payload.get("raw")
        parsed = payload.get("parsed")
        parsing_error = payload.get("parsing_error")
        logger.info(
            "[LCEL][{}][structured]\nraw={}\nparsed={}\nparsing_error={}",
            step_name,
            _truncate_text(_serialize_lcel_payload(raw)),
            _truncate_text(_serialize_lcel_payload(parsed)),
            parsing_error,
        )

    parsing_error = payload.get("parsing_error")
    if parsing_error is not None:
        raise parsing_error
    return payload.get("parsed")


def build_debuggable_structured_llm_chain(step_name: str, prompt: Any, schema: type[BaseModel]) -> Any:
    """构建一个带 LCEL 调试能力的结构化输出链。

    链路结构为：
    - prompt
    - input debug runnable
    - llm.with_structured_output(schema, include_raw=True)
    - unwrap structured result

    设计意图：
    - 让模型直接按 schema 输出，而不是先自由生成再用 JSON parser 猜
    - 同时保留 raw/parsed 调试信息，便于排查到底是 prompt、模型还是解析层出问题
    """

    structured_llm = llm.with_structured_output(
        schema,
        # 这里优先使用 `json_mode`，原因是当前项目接入的是 DashScope OpenAI 兼容接口，
        # 实测 `qwen3.5-flash` 在默认 thinking 模式下对 function calling 的
        # `tool_choice=required/object` 支持不完整，会直接返回 400。
        #
        # `json_mode` 仍然属于 LangChain 的结构化输出能力：
        # - 模型层负责尽量生成 JSON
        # - LangChain 负责按 schema 解析成 Pydantic 对象
        #
        # 结合我们已经收紧的 prompt（明确要求只输出指定 JSON 对象），
        # 这条链路在当前兼容服务上更稳。
        method="json_mode",
        include_raw=True,
    )
    return (
        prompt
        | create_lcel_debug_runnable(step_name, "input")
        | structured_llm
        | RunnableLambda(lambda payload: _unwrap_structured_output(step_name, payload))
    )


def build_debuggable_structured_payload_chain(step_name: str, prompt: Any, schema: type[BaseModel]) -> Any:
    """构建只返回结构化 payload 的 LCEL 链。

    和 `build_debuggable_structured_llm_chain` 的区别是，这里先不做最终的
    `parsed/parsing_error` 解包，而是把 LangChain 返回的 payload 原样交给调用方。

    这样做的目的，是让调用方在解析失败时仍然拿得到：
    - 原始模型输出 `raw`
    - 解析后的半成品 `parsed`
    - 具体错误 `parsing_error`

    有了这三类信息，才能继续做“带错误反馈的纠错重试”。
    """

    structured_llm = llm.with_structured_output(
        schema,
        method="json_mode",
        include_raw=True,
    )
    return prompt | create_lcel_debug_runnable(step_name, "input") | structured_llm


def _extract_payload_parsing_error(payload: Any) -> Exception | None:
    """从结构化输出 payload 中提取解析错误。"""

    if isinstance(payload, dict):
        parsing_error = payload.get("parsing_error")
        if isinstance(parsing_error, Exception):
            return parsing_error
    return None


async def _render_prompt_text(prompt: Any, inputs: Any) -> str:
    """把 prompt 和输入渲染成最终发给模型的文本。"""

    rendered = await prompt.ainvoke(inputs)
    return _serialize_lcel_payload(rendered)


def _build_structured_repair_prompt() -> PromptTemplate:
    """构建结构化输出失败后的纠错 prompt。

    这条 prompt 不再重复业务推理，而是明确告诉模型：
    - 上一次输出为什么失败
    - 原始任务是什么
    - 必须满足什么 schema
    - 这次只能返回合法 JSON
    """

    return PromptTemplate(
        template=(
            "你正在修复一次结构化输出失败。\n"
            "\n"
            "要求：\n"
            "1. 只输出一个合法 JSON 对象。\n"
            "2. 输出必须严格满足给定 JSON Schema。\n"
            "3. 不要输出解释、代码块、前后缀文字。\n"
            "4. 如果原始任务信息不足，也必须返回结构合法的最小结果。\n"
            "\n"
            "原始任务：\n"
            "{original_prompt}\n"
            "\n"
            "上一次模型输出：\n"
            "{bad_output}\n"
            "\n"
            "解析或校验错误：\n"
            "{error_message}\n"
            "\n"
            "目标 JSON Schema：\n"
            "{schema_json}\n"
        ),
        input_variables=["original_prompt", "bad_output", "error_message", "schema_json"],
    )


async def ainvoke_structured_chain_with_retry(
    step_name: str,
    prompt: Any,
    schema: type[BaseModel],
    inputs: Any,
    retry_count: int | None = None,
) -> Any:
    """执行结构化输出链，并在必要时做有限重试。

    当前这条链路的可靠性不是只靠 prompt，而是四层一起工作：
    - Prompt：约束模型只输出指定结构
    - Structured Output：要求 LangChain 按 Pydantic schema 解析
    - Schema 校验：字段缺失、类型不对都会直接报错
    - 有限重试：应对模型偶发偏离格式或瞬时网络波动

    当前实现分两类处理：
    - 普通瞬时失败：按原输入直接重试
    - 结构化解析失败：把原 prompt、模型原输出、错误信息、schema 一起回灌给模型，
      再做一次纠错重试

    这样比“纯同输入重试”更强，因为第二次调用不再只靠运气，而是明确告诉模型：
    “你上一次哪里错了，这次必须改成什么结构。”
    """

    max_retries = _structured_retry_count() if retry_count is None else max(retry_count, 0)
    last_exc: Exception | None = None
    original_chain = build_debuggable_structured_payload_chain(step_name, prompt, schema)
    repair_prompt = _build_structured_repair_prompt()
    original_prompt_text: str | None = None
    schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False, indent=2)

    current_chain = original_chain
    current_inputs = inputs

    for attempt in range(max_retries + 1):
        payload: Any = None
        try:
            if attempt > 0:
                logger.warning(
                    "结构化输出重试: step={} attempt={}/{}",
                    step_name,
                    attempt,
                    max_retries,
                )
            payload = await current_chain.ainvoke(current_inputs)
            return _unwrap_structured_output(step_name, payload)
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "结构化输出失败: step={} attempt={}/{} error={}",
                step_name,
                attempt,
                max_retries,
                exc,
            )
            if attempt >= max_retries:
                raise

            parsing_error = _extract_payload_parsing_error(payload)
            if parsing_error is not None:
                if original_prompt_text is None:
                    original_prompt_text = await _render_prompt_text(prompt, inputs)

                bad_output = _serialize_lcel_payload(payload.get("raw"))
                current_chain = build_debuggable_structured_payload_chain(f"{step_name}:repair", repair_prompt, schema)
                current_inputs = {
                    "original_prompt": original_prompt_text,
                    "bad_output": bad_output,
                    "error_message": str(parsing_error),
                    "schema_json": schema_json,
                }
                logger.warning("结构化输出纠错重试: step={} next_attempt={} strategy=repair_prompt", step_name, attempt + 1)
            else:
                current_chain = original_chain
                current_inputs = inputs
                logger.warning("结构化输出普通重试: step={} next_attempt={} strategy=same_input", step_name, attempt + 1)

    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"structured chain returned unexpectedly without result: {step_name}")
