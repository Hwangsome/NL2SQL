# demo_dw_large

这是项目内留存的可复用测试数仓数据集目录。

生成并导入：

```bash
cd /Users/bill/code/AI/NL2SQL/data-agent
DW_DB_PORT=3307 uv run python -m app.scripts.generate_demo_dw_data --load-db
```

默认生成：

- `dim_region.csv`
- `dim_customer.csv`
- `dim_product.csv`
- `dim_date.csv`
- `fact_order.csv`
- `summary.json`

默认规模：

- `21` 个地区维度
- `600` 个客户
- `120` 个商品
- `1186` 个日期
- `18000` 条订单事实
