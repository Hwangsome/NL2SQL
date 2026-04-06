"use client"

import { Button } from "@/components/ui/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle, EmptyDescription } from "@/components/ui/empty"
import { exportToCsv, copyJson } from "@/lib/export"
import { cn } from "@/lib/utils"
import { Copy, Download, Table as TableIcon, Check } from "lucide-react"
import { useState, useCallback } from "react"

interface ResultTableProps {
  data: Record<string, unknown>[]
}

export function ResultTable({ data }: ResultTableProps) {
  const [copied, setCopied] = useState(false)

  const handleCopyJson = useCallback(async () => {
    const success = await copyJson(data)
    if (success) {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }, [data])

  const handleExportCsv = useCallback(() => {
    const timestamp = new Date().toISOString().slice(0, 19).replace(/[:-]/g, "")
    exportToCsv(data, `query-result-${timestamp}.csv`)
  }, [data])

  if (data.length === 0) {
    return (
      <div className="bg-card border border-border rounded-lg p-6">
        <Empty>
          <EmptyHeader>
            <EmptyMedia>
              <TableIcon className="w-12 h-12 text-muted-foreground/50" />
            </EmptyMedia>
            <EmptyTitle>暂无结果</EmptyTitle>
            <EmptyDescription>查询未返回任何数据</EmptyDescription>
          </EmptyHeader>
        </Empty>
      </div>
    )
  }

  const columns = Object.keys(data[0])

  const isNumeric = (value: unknown): boolean => {
    if (value === null || value === undefined || value === "") return false
    return !isNaN(Number(value))
  }

  const formatValue = (value: unknown): string => {
    if (value === null || value === undefined) return "-"
    if (typeof value === "number") {
      return value.toLocaleString("zh-CN", { maximumFractionDigits: 4 })
    }
    return String(value)
  }

  return (
    <div className="bg-card border border-border rounded-lg overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-secondary/30">
        <div className="flex items-center gap-2">
          <TableIcon className="w-4 h-4 text-primary" />
          <span className="text-sm font-medium text-foreground">明细数据</span>
          <span className="text-xs text-muted-foreground bg-muted px-2 py-0.5 rounded-full">
            {data.length} 条记录
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleCopyJson}
            className="gap-1.5 h-8 text-xs"
          >
            {copied ? (
              <>
                <Check className="w-3.5 h-3.5 text-success" />
                已复制
              </>
            ) : (
              <>
                <Copy className="w-3.5 h-3.5" />
                复制 JSON
              </>
            )}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleExportCsv}
            className="gap-1.5 h-8 text-xs"
          >
            <Download className="w-3.5 h-3.5" />
            导出 CSV
          </Button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow className="bg-secondary/20 hover:bg-secondary/20">
              {columns.map((column) => (
                <TableHead
                  key={column}
                  className="text-xs font-semibold text-foreground whitespace-nowrap"
                >
                  {column}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.map((row, rowIndex) => (
              <TableRow
                key={rowIndex}
                className="hover:bg-secondary/30 transition-colors"
              >
                {columns.map((column) => {
                  const value = row[column]
                  const numeric = isNumeric(value)

                  return (
                    <TableCell
                      key={column}
                      className={cn(
                        "text-sm whitespace-nowrap py-3",
                        numeric && "text-right font-mono",
                        (value === null || value === undefined) && "text-muted-foreground"
                      )}
                    >
                      {formatValue(value)}
                    </TableCell>
                  )
                })}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
