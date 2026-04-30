import jieba.analyse
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.progress import emit_progress, preview_list
from app.agent.state import DataAgentState
from app.core.log import logger


async def extract_keywords(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """
    从用户原始问题中抽取第一批检索关键词。

    输入：
    - state["query"]: 用户输入的自然语言问题。
    - runtime.stream_writer: 用于向前端发送进度事件。

    输出：
    - {"keywords": list[str]}:
      由 jieba 关键词抽取结果和原始 query 本身组成，最终会去重。

    说明：
    - 这里只做“粗粒度关键词抽取”，目的是给后续字段、字段值、指标召回提供初始检索词。
    - 即使 jieba 没有抽到足够理想的词，也会保留原始 query 作为兜底，避免语义丢失。

    示例：
    - 用户问题：`去年华东地区销售额最高的品类是什么`
    - jieba 在 `allow_pos` 限制下，可能抽到：
      - `华东地区`
      - `销售额`
      - `品类`
      - `最高`
    - 然后代码还会额外把原始问题整句加进去：
      - `去年华东地区销售额最高的品类是什么`
    - 最终输出可能类似：
      - `["华东地区", "销售额", "品类", "最高", "去年华东地区销售额最高的品类是什么"]`

    为什么要这样做：
    - 短关键词适合后面做字段/指标/字段值检索；
    - 原始整句可以兜底保留完整语义，避免分词结果太碎。
    """
    writer = runtime.stream_writer
    emit_progress(writer, "抽取关键字", "running", "正在从用户问题里提取检索关键词。")

    query = state["query"]
    # 第 1 步：限制词性范围。
    #
    # 这里只保留更适合作为检索词的词性，尽量过滤“的/什么/怎么样”这类虚词。
    # 业务上我们更想保留的是：
    # - 名词：销售额、品类、地区
    # - 动词/形容词：增长、最高
    #
    # 例子：
    # - 句子：`去年华东地区销售额最高的品类是什么`
    # - 更希望留下：`华东地区`、`销售额`、`品类`、`最高`
    # - 尽量过滤掉：`什么`、`的`
    allow_pos = ("n", "nr", "ns", "nt", "nz", "v", "vn", "a", "an", "eng", "i", "l")

    # 第 2 步：做关键词抽取，并把原始 query 一并放进去。
    #
    # 例子：
    # - extract_tags(query) 可能返回：["华东地区", "销售额", "品类", "最高"]
    # - 加上原始 query 后：
    #   ["华东地区", "销售额", "品类", "最高", "去年华东地区销售额最高的品类是什么"]
    #
    # 这么做的目的是：
    # - 用短词提高召回精度；
    # - 用整句补足上下文，避免短词丢语义。
    keywords = list(set(jieba.analyse.extract_tags(query, allowPOS=allow_pos) + [query]))

    emit_progress(writer, "抽取关键字", "success", f"提取到的关键词：{preview_list(keywords)}")
    logger.info(f"抽取关键字完成: {keywords}")

    # 这里返回的不是一个“普通业务结果”，而是一个“状态增量（state patch）”。
    #
    # 在 `StateGraph` 中，节点函数接收当前 `state`，并通过返回 `dict` 的方式声明：
    # “我要更新 state 中的哪些字段”。
    #
    # 对当前节点来说：
    # - 返回 `{"keywords": keywords}`
    # - 就等价于告诉 LangGraph：
    #   “请把当前步骤产出的关键词列表写入共享状态里的 `keywords` 字段”
    #
    # 随后 LangGraph 会在运行时把这个返回值合并回图状态，因此下游节点会读到：
    # - state["query"]          # 来自初始输入
    # - state["keywords"]       # 来自本节点 return 的结果
    #
    # 例如初始 state 是：
    # {
    #   "query": "统计去年各地区的销售总额"
    # }
    #
    # 本节点返回：
    # {
    #   "keywords": ["统计", "地区", "销售总额", "统计去年各地区的销售总额"]
    # }
    #
    # LangGraph 合并后，下游节点实际看到的 state 近似于：
    # {
    #   "query": "统计去年各地区的销售总额",
    #   "keywords": ["统计", "地区", "销售总额", "统计去年各地区的销售总额"]
    # }
    #
    # 需要注意：
    # - 这里并不是 Python 自动把 return 值写回 state
    # - 真正的 merge 动作是 LangGraph 在编译后的运行时内部完成的
    # - 只有返回的 key 出现在 `DataAgentState` 这类状态 schema 中时，才会被当作合法状态更新
    return {"keywords": keywords}
