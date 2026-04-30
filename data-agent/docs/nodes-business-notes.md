# Data Agent 节点业务笔记

这份文档专门解释 `app/agent/nodes/` 下每个节点在业务上的作用。目标不是重复代码注释，而是把下面几件事说清楚：

- 这个节点为什么存在
- 它接收什么输入
- 它输出什么结果
- 它在整个 NL2SQL 链路里解决什么问题
- 如果拿一个具体问题来走，这一步会发生什么

---

## 1. 先理解整个链路在解决什么问题

这个项目不是“用户一句话，模型直接写 SQL”。

它更像一条分阶段收敛的问数流水线：

1. 先从自然语言里抽关键词
2. 再分别召回字段、字段值、指标
3. 把这些零散结果补齐成结构化上下文
4. 再过滤掉噪声
5. 补时间和数据库信息
6. 生成 SQL
7. 校验 SQL
8. 修正 SQL
9. 执行 SQL
10. 总结成业务结论

图入口在：

- `app/agent/graph.py`

节点实现都在：

- `app/agent/nodes/`

---

## 2. 统一案例

下面所有节点都尽量用同一个例子来解释：

`去年华东地区销售额最高的品类是什么`

这个问题里同时包含了几类信息：

- 指标：`销售额`
- 维度：`品类`
- 过滤值：`华东`
- 时间条件：`去年`
- 分析意图：`最高`

而数据库里未必正好有这些同名字段，所以系统必须把这句话慢慢拆开、补全、约束，最后才能变成 SQL。

---

## 3. 节点总览

### 3.1 节点顺序

1. `extract_keywords`
2. `recall_column`
3. `recall_value`
4. `recall_metric`
5. `merge_retrieved_info`
6. `filter_table`
7. `filter_metric`
8. `add_extra_context`
9. `generate_sql`
10. `validate_sql`
11. `correct_sql`
12. `execute_sql`
13. `summarize_answer`

### 3.2 三个关键设计思想

这个项目里最重要的，不是某个单点节点，而是下面三个设计思想：

1. 多路召回  
   不只召回字段，还要召回值和指标。

2. 上下文收敛  
   不是把所有 schema 都扔给模型，而是逐步收敛到最小必要上下文。

3. SQL 闭环  
   SQL 不是一生成就执行，而是先校验、失败再修正。

---

## 4. `extract_keywords`

文件：

- `app/agent/nodes/extract_keywords.py`

### 4.1 业务作用

这是整条链路的起点。

它的作用不是理解完整业务语义，而是先从用户问题里抽出第一批“适合检索”的词，给后面的召回节点做输入。

### 4.2 为什么需要这一步

用户说的是自然语言，通常会带很多不适合直接检索的词，比如：

- 什么
- 的
- 怎么样
- 帮我看一下

如果后面的检索直接拿整句或这些噪声词去查，召回结果会很乱。

所以这里先做一层关键词抽取，把更像“业务实体和业务动作”的词留下来。

### 4.3 输入

- `state["query"]`

例如：

- `去年华东地区销售额最高的品类是什么`

### 4.4 输出

- `{"keywords": [...]}`  

例如可能输出：

- `["华东地区", "销售额", "品类", "最高", "去年华东地区销售额最高的品类是什么"]`

### 4.5 业务意义

这一层的重点是：

- 给下游召回准备初始检索词
- 尽量过滤虚词
- 但同时保留原始整句，防止分词太碎导致语义丢失

### 4.6 下游影响

这个节点的输出会同时进入：

- `recall_column`
- `recall_value`
- `recall_metric`

---

## 5. `recall_column`

文件：

- `app/agent/nodes/recall_column.py`

### 5.1 业务作用

这一步负责找到“这次问题可能会用到哪些字段”。

### 5.2 为什么不能直接靠字符串匹配

因为用户说的词和数据库字段名经常对不上。

例如：

- 用户说：`品类`
- 库里字段可能叫：`category_name`

再比如：

- 用户说：`销售额`
- 库里可能是：`amount`

所以这里不是做简单包含匹配，而是先扩词，再做向量语义召回。

### 5.3 输入

- `state["query"]`
- `state["keywords"]`
- embedding client
- Qdrant 字段向量库

### 5.4 处理过程

1. 把原始 query 发给 LLM  
   让它产出更像字段名、字段别名的扩展词。

2. 把这些扩展词和上游关键词合并。

3. 对每个词做 embedding。

4. 用 embedding 去 Qdrant 做字段向量检索。

5. 按字段 id 去重。

### 5.5 统一案例里的样子

用户问题：

- `去年华东地区销售额最高的品类是什么`

初始关键词可能是：

- `华东地区`
- `销售额`
- `品类`

LLM 可能扩出：

- `地区`
- `区域`
- `类目`
- `销售金额`

Qdrant 可能召回：

- `dim_region.region_name`
- `dim_product.category_name`
- `fact_order.amount`
- `dim_date.year`

### 5.6 输出

- `{"retrieved_columns": list[ColumnInfo]}`

### 5.7 业务意义

这一步解决的是：

“用户说的业务词，可能落在数据库里的哪些列上？”

---

## 6. `recall_value`

文件：

- `app/agent/nodes/recall_value.py`

### 6.1 业务作用

这一步负责找到：

“用户提到的某些词，可能是哪个字段上的值。”

### 6.2 为什么需要字段值召回

很多时候，用户问题的关键信息根本不是字段名，而是字段值。

例如：

- `华东`
- `黄金会员`
- `手机`

这些词不是 schema 名字，而是业务数据本身的取值。

如果不做字段值召回，系统容易只知道有个地区字段，但不知道这次到底要筛哪个地区。

### 6.3 输入

- `state["query"]`
- `state["keywords"]`
- Elasticsearch 字段值索引

### 6.4 处理过程

1. 把 query 发给 LLM，生成更适合查“值”的关键词。

2. 和上游关键词合并。

3. 对每个词去 ES 查询。

4. 把命中的值对象按 id 去重。

### 6.5 统一案例里的样子

用户问题：

- `去年华东地区销售额最高的品类是什么`

可能扩出的值查询词：

- `华东`
- `地区`
- `区域`

ES 可能命中：

- `dim_region.region_name = 华东`

### 6.6 输出

- `{"retrieved_values": list[ValueInfo]}`

### 6.7 业务意义

这一步解决的是：

“用户这次提到的过滤值，可能属于哪个字段？”

---

## 7. `recall_metric`

文件：

- `app/agent/nodes/recall_metric.py`

### 7.1 业务作用

这一步负责识别：

“用户问的是哪个业务指标。”

### 7.2 为什么指标要单独召回

因为业务问题里经常是指标驱动，而不是字段驱动。

例如用户会说：

- 销售额
- 订单量
- 客单价
- 复购率

这些词在业务上很明确，但数据库里未必就是一个同名字段。

有些指标甚至不是单列，而是一套口径定义。

### 7.3 输入

- `state["query"]`
- `state["keywords"]`
- embedding client
- Qdrant 指标向量库

### 7.4 处理过程

1. 让 LLM 把 query 扩成更像指标别名的词。

2. 和关键词合并。

3. 对每个词做 embedding。

4. 去 Qdrant 召回指标。

5. 按指标 id 去重。

### 7.5 统一案例里的样子

用户问题：

- `去年华东地区销售额最高的品类是什么`

可能扩出的指标词：

- `销售金额`
- `成交金额`
- `GMV`

召回到的指标可能是：

- `销售额`

### 7.6 输出

- `{"retrieved_metrics": list[MetricInfo]}`

### 7.7 业务意义

这一步解决的是：

“用户问的业务口径，系统有没有理解对。”

---

## 8. `merge_retrieved_info`

文件：

- `app/agent/nodes/merge_retrieved_info.py`

### 8.1 业务作用

这是整个项目最关键的节点之一。

它的作用不是简单把三路召回结果拼在一起，而是把它们补齐成一份真正适合 SQL 生成的上下文。

### 8.2 它为什么重要

上游三路召回拿到的是三种不同粒度的信息：

- 字段
- 值
- 指标

但 SQL 生成真正需要的是：

- 候选表
- 候选字段
- 字段示例值
- 候选指标
- 可用 join key

所以这里必须做一次“业务补齐”。

### 8.3 输入

- `retrieved_columns`
- `retrieved_values`
- `retrieved_metrics`
- 元数据仓库

### 8.4 处理过程

1. 字段先按 id 去重。

2. 把指标依赖的字段补回来。  
   比如指标是“销售额”，它依赖 `amount`、`order_id`、日期字段等。

3. 把值召回反向补到字段上，并把命中的值写进字段的 `examples`。  
   例如 `华东` 写回 `region_name.examples`。

4. 按表聚合字段。

5. 为每张候选表补 key columns。  
   比如 `product_id`、`region_id`、`date_id` 这些 join 关键列。

6. 整理成 prompt 友好的 `table_infos` 和 `metric_infos`。

### 8.5 统一案例里的样子

假设上游有：

- 字段：
  - `fact_order.amount`
  - `dim_product.category_name`
- 值：
  - `dim_region.region_name = 华东`
- 指标：
  - `销售额(relevant_columns=[fact_order.amount, fact_order.order_id, dim_date.date])`

这一节点处理后，可能得到：

- `fact_order(amount, order_id, product_id, region_id, date_id, ...)`
- `dim_product(category_name, product_id, ...)`
- `dim_region(region_name, region_id, examples=["华东", ...])`
- `dim_date(date, year, ...)`

以及：

- `销售额`

### 8.6 输出

- `{"table_infos": [...], "metric_infos": [...]}`

### 8.7 业务意义

这一步解决的是：

“怎么把零散召回结果变成一份真正能拿来写 SQL 的上下文。”

---

## 9. `filter_table`

文件：

- `app/agent/nodes/filter_table.py`

### 9.1 业务作用

这一步负责从候选表和候选字段里继续裁剪，保留这次问题真正需要的部分。

### 9.2 为什么合并后还要再过滤

因为合并阶段是偏召回思路，原则上宁可多给一点，也不能漏太多。

但进入 SQL 生成前，给模型的上下文不能太宽，否则容易：

- 选错字段
- 多余 join
- 被噪声干扰

### 9.3 输入

- `query`
- `table_infos`

### 9.4 处理过程

1. 把候选表结构发给 LLM。

2. 让它返回这次问题真正需要的表和字段映射。

3. 代码按这个映射裁剪 `table_infos`。

### 9.5 统一案例里的样子

候选表可能有：

- `fact_order(amount, order_id, product_id, region_id, date_id)`
- `dim_product(category_name, brand_name, product_id)`
- `dim_region(region_name, region_id)`
- `dim_date(date_id, year, month)`

过滤后可能保留：

- `fact_order(amount, product_id, region_id, date_id)`
- `dim_product(category_name, product_id)`
- `dim_region(region_name, region_id)`
- `dim_date(date_id, year)`

### 9.6 输出

- 裁剪后的 `table_infos`

### 9.7 业务意义

这一步解决的是：

“哪些表和列是这次问题真正要用的，哪些只是召回时顺带命中的噪声。”

---

## 10. `filter_metric`

文件：

- `app/agent/nodes/filter_metric.py`

### 10.1 业务作用

这一步负责从候选指标里保留当前问题真正相关的那个或几个指标。

### 10.2 为什么需要这一步

因为指标召回阶段为了防漏召回，通常会放得比较宽。

例如一个问题里问“销售额”，可能也会顺带召回：

- 订单量
- 客单价
- 销量

这些指标不一定都该进入最终 SQL。

### 10.3 输入

- `query`
- `metric_infos`

### 10.4 处理过程

1. 把候选指标交给 LLM。

2. 让它判断当前问题真正要用哪几个指标。

3. 按指标名称过滤。

### 10.5 统一案例里的样子

候选指标有：

- `销售额`
- `订单量`
- `客单价`

当前问题问的是：

- `去年华东地区销售额最高的品类是什么`

最终保留：

- `销售额`

### 10.6 输出

- 裁剪后的 `metric_infos`

### 10.7 业务意义

这一步解决的是：

“系统是否把用户真正想问的业务口径锁对了。”

---

## 11. `add_extra_context`

文件：

- `app/agent/nodes/add_extra_context.py`

### 11.1 业务作用

这一步补两类系统级上下文：

- 当前日期信息
- 数据库方言和版本信息

### 11.2 为什么需要它

用户经常说：

- 去年
- 今年
- 本月
- 本季度

这些词不是 SQL，必须转换成明确时间。

另外生成 SQL 时，模型还要知道当前数据库是什么方言，比如 MySQL、PostgreSQL、SQLite 的语法不一样。

### 11.3 输入

- 数据库仓库

### 11.4 输出

- `date_info`
- `db_info`

### 11.5 统一案例里的样子

如果系统当前日期是：

- `2026-04-13`

那么输出可能是：

- `date = 2026-04-13`
- `year = 2026`
- `last_year = 2025`
- `current_quarter = Q2`

如果数据库是 MySQL 8：

- `dialect = mysql`
- `version = 8.x`

### 11.6 业务意义

这一步解决的是：

“模型不能自己随便猜今年/去年，也不能假设数据库方言。”

---

## 12. `generate_sql`

文件：

- `app/agent/nodes/generate_sql.py`

### 12.1 业务作用

这是把前面所有上下文真正收束成 SQL 的核心节点。

### 12.2 输入

- `query`
- `table_infos`
- `metric_infos`
- `date_info`
- `db_info`

### 12.3 处理过程

1. 先把 query 里的相对时间展开成明确提示。  
   例如把“去年”补成“去年=2025年”。

2. 把筛选后的表、指标、日期、数据库上下文一起发给 LLM。

3. LLM 返回 SQL。

4. 代码再做一次清洗，把 markdown 代码块去掉。

### 12.4 统一案例里的样子

输入上下文已经基本收敛为：

- 表：
  - `fact_order`
  - `dim_product`
  - `dim_region`
  - `dim_date`
- 关键字段：
  - `amount`
  - `category_name`
  - `region_name`
  - `year`
- 指标：
  - `销售额`
- 时间：
  - `去年 = 2025`

这时模型生成的 SQL 才更有可能靠谱。

### 12.5 输出

- `{"sql": "..."}`

### 12.6 业务意义

这一步解决的是：

“如何在相对受控的上下文里，把业务问题落成数据库可执行语句。”

---

## 13. `validate_sql`

文件：

- `app/agent/nodes/validate_sql.py`

### 13.1 业务作用

在正式执行前验证 SQL 是否可执行。

### 13.2 为什么不直接执行

因为 LLM 生成的第一版 SQL 不一定是对的。

常见问题包括：

- 表名错
- 字段名错
- join 条件错
- 方言不对

如果直接执行，不仅容易报错，也不利于后面自动修正。

### 13.3 输入

- `sql`

### 13.4 输出

两种情况：

1. 通过  
   - `{"error": None}`

2. 不通过  
   - `{"error": "具体错误信息"}`

### 13.5 业务意义

这一步解决的是：

“生成出来的 SQL 到底是不是数据库能接受的。”

---

## 14. `correct_sql`

文件：

- `app/agent/nodes/correct_sql.py`

### 14.1 业务作用

如果 SQL 校验失败，这一步负责根据报错和上下文修正 SQL。

### 14.2 为什么要单独修正，而不是直接重生成

因为这里已经有：

- 当前失败 SQL
- 数据库报错
- 已经筛好的上下文

用这些信息做定点修复，通常比完全重写更稳定。

### 14.3 输入

- 原始 query
- 当前 SQL
- error
- table_infos
- metric_infos
- date_info
- db_info

### 14.4 统一案例里的样子

例如原 SQL 写成了：

- `fo.sales_amount`

但数据库报错说：

- `Unknown column 'fo.sales_amount'`

模型看到报错和上下文后，可能修成：

- `fo.amount`

### 14.5 输出

- 修正后的 `sql`

### 14.6 业务意义

这一步解决的是：

“第一版 SQL 有问题时，系统如何自动继续往前走，而不是直接失败。”

---

## 15. `execute_sql`

文件：

- `app/agent/nodes/execute_sql.py`

### 15.1 业务作用

真正执行 SQL，拿到结果集。

### 15.2 输入

- `sql`

### 15.3 输出

- `{"result_rows": [...]}`  

例如：

- `[{"category_name": "手机", "sales_amount": 128000}]`

### 15.4 附加行为

它还会把：

- 返回总行数
- 首行样例

写进 progress detail，方便前端预览。

### 15.5 业务意义

这一步解决的是：

“SQL 终于落到真实数仓里，系统拿到了真实业务数据。”

---

## 16. `summarize_answer`

文件：

- `app/agent/nodes/summarize_answer.py`

### 16.1 业务作用

把 SQL 结果翻译成用户能直接看的业务结论，并流式输出给前端。

### 16.2 为什么需要这一步

业务同学通常不想看：

- 原始 SQL
- 一堆表格记录

他们更想直接看到：

- 结论是什么
- 时间范围是什么
- 有没有数据

### 16.3 输入

- `query`
- `sql`
- `result_rows`
- `date_info`

### 16.4 处理过程

1. 如果有“去年/今年/本月/本季度”，先生成时间解释。

2. 把 query、SQL、结果集发给 LLM，让它总结。

3. 结果按流式 chunk 写给前端。

4. 如果 LLM 失败，退回规则模板总结。

5. 最后再把完整结果包写给前端。

### 16.5 统一案例里的样子

如果结果是：

- `[{"category_name": "手机", "sales_amount": 128000}]`

系统可能生成：

- `这里的“去年”指 2025 年（相对于当前日期 2026-04-13）。华东地区销售额最高的品类是手机，销售额为 128000。`

### 16.6 业务意义

这一步解决的是：

“如何把结构化数据翻译成业务人员可直接消费的自然语言结论。”

---

## 17. 最后把整条链路串起来

如果要用一句更完整的话概括整条节点链路，可以这样理解：

1. `extract_keywords`  
   先把自然语言问题变成可检索的词。

2. `recall_column / recall_value / recall_metric`  
   分别从字段、值、指标三个维度理解用户在问什么。

3. `merge_retrieved_info`  
   把零散召回结果补成可用上下文。

4. `filter_table / filter_metric`  
   把上下文继续压缩到最小必要范围。

5. `add_extra_context`  
   把时间和数据库信息补齐。

6. `generate_sql`  
   生成 SQL。

7. `validate_sql / correct_sql`  
   保证 SQL 能跑。

8. `execute_sql`  
   拿到真实数据。

9. `summarize_answer`  
   把数据翻译成业务结论。

---

## 18. 这份文档适合怎么用

如果你是为了看懂代码，建议顺序：

1. 先看 `graph.py`
2. 再看本文件
3. 最后再去看节点代码

如果你是为了准备面试，建议搭配下面这份文档一起看：

- `docs/interview-qa.md`
