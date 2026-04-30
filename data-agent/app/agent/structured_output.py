from pydantic import BaseModel, Field


class KeywordExpansionOutput(BaseModel):
    """扩词节点统一使用的结构化输出 schema。

    这里把三个扩词节点的输出协议统一收敛为一个对象：

    ```json
    {
      "keywords": ["地区", "区域", "销售额"]
    }
    ```

    这样做有两个目的：
    - 让 prompt、模型输出和代码解析共享同一份明确 schema
    - 使用 `with_structured_output()` 时，让 LLM 直接面向结构化结果生成

    注意：
    - 现在不再接受“直接返回数组”或其他兼容格式
    - 如果模型没有按 schema 输出，会在结构化解析层暴露出来
    """

    keywords: list[str] = Field(description="扩展得到的检索关键词列表，元素必须是字符串。")


class TableSelectionOutput(BaseModel):
    """表字段筛选节点的结构化输出 schema。"""

    tables: dict[str, list[str]] = Field(
        description="需要保留的表与字段映射。key 是表名，value 是该表需要保留的字段名数组。"
    )


class MetricSelectionOutput(BaseModel):
    """指标筛选节点的结构化输出 schema。"""

    metrics: list[str] = Field(description="需要保留的候选指标名称列表。")
