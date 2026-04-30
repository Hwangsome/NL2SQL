import yaml
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.lcel_debug import ainvoke_structured_chain_with_retry
from app.agent.progress import emit_progress, preview_list
from app.agent.state import DataAgentState
from app.agent.structured_output import MetricSelectionOutput
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


async def filter_metric(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """
    从候选指标中保留与当前问题强相关的指标。

    输入：
    - state["query"]: 用户自然语言问题。
    - state.get("metric_infos", []): `merge_retrieved_info` 产出的候选指标。
    - runtime.stream_writer: 进度事件输出。

    输出：
    - {"metric_infos": list[MetricInfoState]}:
      仅保留被 LLM 选中的指标列表。

    说明：
    - 这里的目标是减少“相似但不相关”的业务指标干扰。
    - prompt 期望返回 `{"metrics": [...]}`，代码按名称对白名单过滤。

    示例：
    - 上游候选指标可能有：
      - `销售额`
      - `订单量`
      - `客单价`
    - 用户问题：`去年华东地区销售额最高的品类是什么`
    - LLM 过滤后可能只保留：
      - `{"metrics": ["销售额"]}`
    - 最终输出：
      - `{"metric_infos": [{"name": "销售额", ...}]}`

    业务意义：
    - 召回阶段为了避免漏掉指标，通常会放得宽；
    - 这里再收窄一次，可以减少模型把“订单量”“客单价”等相似概念误带进 SQL。
    """
    writer = runtime.stream_writer
    emit_progress(writer, "过滤指标", "running", "正在筛选本次问题真正相关的指标。")

    query = state["query"]
    metric_infos = state.get("metric_infos", [])

    try:
        # 第 1 步：把候选指标交给 LLM，判断这次问题真正对应哪一个业务口径。
        #
        # 例子：
        # - 问题里明确说“销售额”，那 `订单量` 和 `客单价` 通常应被排除
        prompt = PromptTemplate(template=load_prompt("filter_metric_info"), input_variables=["query", "metric_infos"])
        result = await ainvoke_structured_chain_with_retry(
            "filter_metric",
            prompt,
            MetricSelectionOutput,
            {"query": query, "metric_infos": yaml.dump(metric_infos, allow_unicode=True, sort_keys=False)},
        )

        allowed = set(result.metrics)
        # 第 2 步：只保留模型明确选择的指标名。
        #
        # 例子：
        # - allowed = {"销售额"}
        # - 原候选 = [销售额, 订单量, 客单价]
        # - 过滤后 = [销售额]
        metric_infos = [metric_info for metric_info in metric_infos if metric_info["name"] in allowed]

        emit_progress(
            writer,
            "过滤指标",
            "success",
            f"保留指标：{preview_list([metric['name'] for metric in metric_infos])}",
        )
        logger.info(f"过滤指标完成: {[metric['name'] for metric in metric_infos]}")
        return {"metric_infos": metric_infos}
    except Exception as exc:
        emit_progress(writer, "过滤指标", "error", f"指标筛选失败：{exc}")
        raise
