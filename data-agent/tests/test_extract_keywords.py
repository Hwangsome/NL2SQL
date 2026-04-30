from types import SimpleNamespace

import jieba.analyse
import pytest

import app.agent.nodes.extract_keywords as extract_keywords_module


ALLOW_POS = ("n", "nr", "ns", "nt", "nz", "v", "vn", "a", "an", "eng", "i", "l")


def test_jieba_extract_tags_with_allow_pos_filters_noise_words():
    query = "去年华东地区销售额最高的品类是什么"

    # ['品类', '华东地区', '销售额', '去年', '最高', '什么']
    default_keywords = jieba.analyse.extract_tags(query, topK=20)
    # ['品类', '华东地区', '销售额', '最高']
    filtered_keywords = jieba.analyse.extract_tags(query, topK=20, allowPOS=ALLOW_POS)

    assert "品类" in filtered_keywords
    assert "销售额" in filtered_keywords
    assert "最高" in filtered_keywords
    assert "什么" in default_keywords
    assert "什么" not in filtered_keywords
    assert "去年" in default_keywords
    assert "去年" not in filtered_keywords


@pytest.mark.asyncio
async def test_extract_keywords_deduplicates_tags_and_keeps_original_query(monkeypatch):
    captured = {}

    def fake_extract_tags(query: str, allowPOS=None):
        captured["query"] = query
        captured["allowPOS"] = allowPOS
        return ["销售额", "华东", "销售额"]

    monkeypatch.setattr(extract_keywords_module.jieba.analyse, "extract_tags", fake_extract_tags)

    events = []
    runtime = SimpleNamespace(stream_writer=events.append)
    state = {"query": "去年华东销售额"}

    result = await extract_keywords_module.extract_keywords(state, runtime)

    assert set(result["keywords"]) == {"销售额", "华东", "去年华东销售额"}
    assert captured["query"] == "去年华东销售额"
    assert captured["allowPOS"] == ALLOW_POS
    assert [event["status"] for event in events] == ["running", "success"]
    assert all(event["step"] == "抽取关键字" for event in events)
    assert "提取到的关键词" in events[1]["detail"]


@pytest.mark.asyncio
async def test_extract_keywords_falls_back_to_original_query_when_no_tag_found(monkeypatch):
    monkeypatch.setattr(extract_keywords_module.jieba.analyse, "extract_tags", lambda query, allowPOS=None: [])

    runtime = SimpleNamespace(stream_writer=lambda payload: None)
    state = {"query": "最近一个月销售趋势"}

    result = await extract_keywords_module.extract_keywords(state, runtime)

    assert result["keywords"] == ["最近一个月销售趋势"]
