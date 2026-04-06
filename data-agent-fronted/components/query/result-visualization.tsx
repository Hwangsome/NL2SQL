"use client"

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  XAxis,
  YAxis,
} from "recharts"
import { BarChart3, LineChart as LineChartIcon, PieChart as PieChartIcon } from "lucide-react"

import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"

interface ResultVisualizationProps {
  data: Record<string, unknown>[]
}

type ChartKind = "line" | "bar" | "pie"

type ChartPlan = {
  kind: ChartKind
  title: string
  description: string
  data: Record<string, string | number>[]
  categoryKey?: string
  seriesKeys: string[]
  config: ChartConfig
}

const PIE_COLORS = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
]

function isNumeric(value: unknown): value is number | string {
  if (value === null || value === undefined || value === "") return false
  const normalized = typeof value === "string" ? value.replace(/,/g, "") : value
  return Number.isFinite(Number(normalized))
}

function toNumber(value: unknown): number {
  if (!isNumeric(value)) return 0
  return Number(typeof value === "string" ? value.replace(/,/g, "") : value)
}

function formatMetric(value: number): string {
  return value.toLocaleString("zh-CN", { maximumFractionDigits: 2 })
}

function isTimeKey(key: string): boolean {
  return /date|day|month|year|week|time|日期|时间|月份|年度|年份|周/.test(key.toLowerCase())
}

function getChartPlan(rows: Record<string, unknown>[]): ChartPlan | null {
  if (rows.length === 0) return null

  const columns = Object.keys(rows[0])
  const numericKeys = columns.filter((column) => rows.some((row) => isNumeric(row[column])))
  const dimensionKeys = columns.filter((column) => !numericKeys.includes(column))

  if (rows.length === 1) {
    if (numericKeys.length < 2) return null

    const data = numericKeys.map((key) => ({
      metric: key,
      value: toNumber(rows[0][key]),
    }))

    const config = Object.fromEntries(
      numericKeys.map((key, index) => [
        key,
        { label: key, color: PIE_COLORS[index % PIE_COLORS.length] },
      ]),
    ) as ChartConfig

    return {
      kind: "bar",
      title: "关键指标对比",
      description: "单条结果时，展示当前返回的关键指标值，方便业务快速判断。",
      data,
      categoryKey: "metric",
      seriesKeys: ["value"],
      config: {
        value: { label: "数值", color: "var(--chart-1)" },
        ...config,
      },
    }
  }

  if (dimensionKeys.length === 0 || numericKeys.length === 0) {
    return null
  }

  const categoryKey = dimensionKeys[0]
  const primaryMetrics = numericKeys.slice(0, Math.min(numericKeys.length, 2))

  const mappedRows = rows.map((row) => {
    const chartRow: Record<string, string | number> = {
      [categoryKey]: String(row[categoryKey] ?? "-"),
    }

    for (const metric of primaryMetrics) {
      chartRow[metric] = toNumber(row[metric])
    }

    return chartRow
  })

  const config = Object.fromEntries(
    primaryMetrics.map((metric, index) => [
      metric,
      {
        label: metric,
        color: PIE_COLORS[index % PIE_COLORS.length],
      },
    ]),
  ) as ChartConfig

  if (primaryMetrics.length === 1 && rows.length <= 6) {
    const metric = primaryMetrics[0]
    return {
      kind: "pie",
      title: "占比概览",
      description: `按 ${categoryKey} 展示 ${metric} 的分布，占比关系更直观。`,
      data: mappedRows,
      categoryKey,
      seriesKeys: [metric],
      config,
    }
  }

  return {
    kind: isTimeKey(categoryKey) ? "line" : "bar",
    title: isTimeKey(categoryKey) ? "趋势图" : "对比图",
    description: isTimeKey(categoryKey)
      ? `按 ${categoryKey} 展示变化趋势，适合业务查看增长或波动。`
      : `按 ${categoryKey} 展示核心指标对比，适合销售和业务快速识别差异。`,
    data: mappedRows,
    categoryKey,
    seriesKeys: primaryMetrics,
    config,
  }
}

export function ResultVisualization({ data }: ResultVisualizationProps) {
  const plan = getChartPlan(data)

  if (!plan) {
    return null
  }

  const categoryKey = plan.categoryKey

  const totalValue = plan.seriesKeys.reduce(
    (sum, key) => sum + plan.data.reduce((innerSum, row) => innerSum + toNumber(row[key]), 0),
    0,
  )

  const topPoint =
    categoryKey && plan.seriesKeys.length > 0
      ? [...plan.data].sort((left, right) => toNumber(right[plan.seriesKeys[0]]) - toNumber(left[plan.seriesKeys[0]]))[0]
      : null

  let chartContent = null

  if (plan.kind === "line" && categoryKey) {
    chartContent = (
      <LineChart data={plan.data} margin={{ top: 12, right: 12, left: 0, bottom: 0 }}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey={categoryKey} tickLine={false} axisLine={false} minTickGap={24} />
        <YAxis tickLine={false} axisLine={false} width={72} />
        <ChartTooltip content={<ChartTooltipContent />} />
        {plan.seriesKeys.length > 1 ? (
          <ChartLegend content={<ChartLegendContent />} />
        ) : null}
        {plan.seriesKeys.map((key) => (
          <Line
            key={key}
            type="monotone"
            dataKey={key}
            stroke={`var(--color-${key})`}
            strokeWidth={2.5}
            dot={{ r: 3 }}
            activeDot={{ r: 5 }}
          />
        ))}
      </LineChart>
    )
  } else if (plan.kind === "bar" && categoryKey) {
    chartContent = (
      <BarChart data={plan.data} margin={{ top: 12, right: 12, left: 0, bottom: 0 }}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey={categoryKey} tickLine={false} axisLine={false} minTickGap={24} />
        <YAxis tickLine={false} axisLine={false} width={72} />
        <ChartTooltip content={<ChartTooltipContent />} />
        {plan.seriesKeys.length > 1 ? (
          <ChartLegend content={<ChartLegendContent />} />
        ) : null}
        {plan.seriesKeys.map((key) => (
          <Bar key={key} dataKey={key} fill={`var(--color-${key})`} radius={[10, 10, 3, 3]} />
        ))}
      </BarChart>
    )
  } else if (plan.kind === "pie" && categoryKey) {
    chartContent = (
      <PieChart>
        <ChartTooltip
          content={<ChartTooltipContent nameKey={plan.seriesKeys[0]} labelKey={categoryKey} hideIndicator />}
        />
        <ChartLegend content={<ChartLegendContent nameKey={categoryKey} />} />
        <Pie
          data={plan.data}
          dataKey={plan.seriesKeys[0]}
          nameKey={categoryKey}
          innerRadius={55}
          outerRadius={105}
          paddingAngle={2}
        >
          {plan.data.map((entry, index) => (
            <Cell key={`${String(entry[categoryKey])}-${index}`} fill={PIE_COLORS[index % PIE_COLORS.length]} />
          ))}
        </Pie>
      </PieChart>
    )
  }

  if (!chartContent) {
    return null
  }

  return (
    <div className="space-y-4 rounded-[24px] border border-border/70 bg-background/45 p-4 sm:p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground">图表解读</p>
          <div className="mt-2 flex items-center gap-2">
            {plan.kind === "line" ? (
              <LineChartIcon className="h-4 w-4 text-primary" />
            ) : plan.kind === "pie" ? (
              <PieChartIcon className="h-4 w-4 text-primary" />
            ) : (
              <BarChart3 className="h-4 w-4 text-primary" />
            )}
            <p className="text-sm font-semibold text-foreground sm:text-base">{plan.title}</p>
          </div>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">{plan.description}</p>
        </div>

        <div className="grid gap-2 sm:min-w-[230px]">
          <div className="rounded-2xl border border-border/70 bg-card/90 px-4 py-3">
            <p className="text-xs text-muted-foreground">当前图表覆盖数据</p>
            <p className="mt-1 text-lg font-semibold text-foreground">{plan.data.length} 个数据点</p>
          </div>
          <div className="rounded-2xl border border-border/70 bg-card/90 px-4 py-3">
            <p className="text-xs text-muted-foreground">指标总览</p>
            <p className="mt-1 text-lg font-semibold text-foreground">{formatMetric(totalValue)}</p>
            {topPoint && categoryKey ? (
              <p className="mt-1 text-xs text-muted-foreground">
                最高项：{String(topPoint[categoryKey])} / {formatMetric(toNumber(topPoint[plan.seriesKeys[0]]))}
              </p>
            ) : null}
          </div>
        </div>
      </div>

      <ChartContainer config={plan.config} className="h-[280px] w-full sm:h-[340px]">
        {chartContent}
      </ChartContainer>
    </div>
  )
}
