from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel

import app.agent.lcel_debug as lcel_debug


class KeywordSchema(BaseModel):
    """测试用结构化 schema。"""

    keywords: list[str]


class FakeLLM:
    """一个最小可控的假 LLM。

    `lcel_debug` 里的结构化链最终会调用：
    `llm.with_structured_output(..., include_raw=True)`

    这个 fake 只实现这一个接口，并把每次真正收到的 prompt 文本记录下来，
    方便断言“第二次是否真的走了 repair prompt”。
    """

    def __init__(self, handler):
        self._handler = handler
        self.calls: list[str] = []

    def with_structured_output(self, schema: type[BaseModel], method: str, include_raw: bool):
        assert method == "json_mode"
        assert include_raw is True

        async def _invoke(prompt_value: Any) -> dict[str, Any]:
            rendered = lcel_debug._serialize_lcel_payload(prompt_value)
            self.calls.append(rendered)
            return await self._handler(rendered, schema)

        return RunnableLambda(_invoke)


@pytest.mark.asyncio
async def test_same_input_retry_retries_after_transient_error(monkeypatch):
    """普通瞬时失败时，应按原输入直接重试。"""

    attempts = {"count": 0}

    async def fake_handler(rendered_prompt: str, schema: type[BaseModel]) -> dict[str, Any]:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("temporary upstream failure")
        return {
            "raw": AIMessage(content='{"keywords":["地区","销售额"]}'),
            "parsed": schema(keywords=["地区", "销售额"]),
            "parsing_error": None,
        }

    fake_llm = FakeLLM(fake_handler)
    monkeypatch.setattr(lcel_debug, "llm", fake_llm)
    monkeypatch.setenv("LCEL_STRUCTURED_RETRY_COUNT", "1")

    prompt = PromptTemplate(
        template="请扩展查询关键词。问题：{query}",
        input_variables=["query"],
    )

    result = await lcel_debug.ainvoke_structured_chain_with_retry(
        "unit_test_same_input_retry",
        prompt,
        KeywordSchema,
        {"query": "统计去年各地区的销售总额"},
    )

    assert result.keywords == ["地区", "销售额"]
    assert attempts["count"] == 2
    # 两次收到的内容应该一致，因为这里走的是“同输入重试”。
    assert len(fake_llm.calls) == 2
    assert fake_llm.calls[0] == fake_llm.calls[1]
    assert "统计去年各地区的销售总额" in fake_llm.calls[0]


@pytest.mark.asyncio
async def test_repair_retry_uses_error_feedback_prompt(monkeypatch):
    """结构化解析失败后，应切换到带错误反馈的 repair prompt。"""

    attempts = {"count": 0}

    async def fake_handler(rendered_prompt: str, schema: type[BaseModel]) -> dict[str, Any]:
        attempts["count"] += 1
        if attempts["count"] == 1:
            # 第一次故意返回一个带 parsing_error 的 payload，模拟 LangChain
            # 已经拿到了原始输出，但无法按 schema 成功解析。
            return {
                "raw": AIMessage(content='["地区","销售额"]'),
                "parsed": None,
                "parsing_error": ValueError("Input should be an object with field `keywords`"),
            }

        # 第二次要求一定是 repair prompt，否则说明没有真正走纠错重试。
        assert "你正在修复一次结构化输出失败" in rendered_prompt
        assert "上一次模型输出" in rendered_prompt
        assert '["地区","销售额"]' in rendered_prompt
        assert "Input should be an object with field `keywords`" in rendered_prompt
        assert "目标 JSON Schema" in rendered_prompt
        return {
            "raw": AIMessage(content='{"keywords":["地区","区域","销售额"]}'),
            "parsed": schema(keywords=["地区", "区域", "销售额"]),
            "parsing_error": None,
        }

    fake_llm = FakeLLM(fake_handler)
    monkeypatch.setattr(lcel_debug, "llm", fake_llm)
    monkeypatch.setenv("LCEL_STRUCTURED_RETRY_COUNT", "1")

    prompt = PromptTemplate(
        template="请把这个问题扩展成字段召回关键词：{query}",
        input_variables=["query"],
    )

    result = await lcel_debug.ainvoke_structured_chain_with_retry(
        "unit_test_repair_retry",
        prompt,
        KeywordSchema,
        {"query": "统计去年各地区的销售总额"},
    )

    assert result.keywords == ["地区", "区域", "销售额"]
    assert attempts["count"] == 2
    assert len(fake_llm.calls) == 2
    assert fake_llm.calls[0] != fake_llm.calls[1]
    assert "请把这个问题扩展成字段召回关键词" in fake_llm.calls[0]
    assert "你正在修复一次结构化输出失败" in fake_llm.calls[1]


@pytest.mark.asyncio
async def test_retry_count_zero_disables_retry(monkeypatch):
    """当重试次数为 0 时，第一次失败应直接抛出。"""

    async def fake_handler(rendered_prompt: str, schema: type[BaseModel]) -> dict[str, Any]:
        return {
            "raw": AIMessage(content='["地区","销售额"]'),
            "parsed": None,
            "parsing_error": ValueError("invalid structured output"),
        }

    fake_llm = FakeLLM(fake_handler)
    monkeypatch.setattr(lcel_debug, "llm", fake_llm)
    monkeypatch.setenv("LCEL_STRUCTURED_RETRY_COUNT", "0")

    prompt = PromptTemplate(
        template="问题：{query}",
        input_variables=["query"],
    )

    with pytest.raises(ValueError, match="invalid structured output"):
        await lcel_debug.ainvoke_structured_chain_with_retry(
            "unit_test_no_retry",
            prompt,
            KeywordSchema,
            {"query": "统计去年各地区的销售总额"},
        )

    assert len(fake_llm.calls) == 1
