"use client"

import { Database, MessageSquareText, BarChart3, Zap } from "lucide-react"

export function WelcomeState() {
  return (
    <div className="text-center py-8 sm:py-12">
      <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-primary/10 border border-primary/20 mb-6">
        <Database className="w-8 h-8 text-primary" />
      </div>
      
      <h2 className="text-xl sm:text-2xl font-semibold text-foreground mb-2">
        像和分析师对话一样提问
      </h2>
      <p className="text-muted-foreground mb-8 max-w-md mx-auto">
        输入一个业务问题，系统会流式返回分析结论，并附上结构化查询结果。
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 max-w-2xl mx-auto">
        <div className="p-4 rounded-lg bg-secondary/30 border border-border">
          <MessageSquareText className="w-6 h-6 text-primary mx-auto mb-2" />
          <h3 className="text-sm font-medium text-foreground mb-1">自然语言查询</h3>
          <p className="text-xs text-muted-foreground">
            用业务语言直接发问
          </p>
        </div>
        <div className="p-4 rounded-lg bg-secondary/30 border border-border">
          <Zap className="w-6 h-6 text-primary mx-auto mb-2" />
          <h3 className="text-sm font-medium text-foreground mb-1">智能 SQL 生成</h3>
          <p className="text-xs text-muted-foreground">
            自动完成召回、建模和 SQL 生成
          </p>
        </div>
        <div className="p-4 rounded-lg bg-secondary/30 border border-border">
          <BarChart3 className="w-6 h-6 text-primary mx-auto mb-2" />
          <h3 className="text-sm font-medium text-foreground mb-1">结论 + 数据</h3>
          <p className="text-xs text-muted-foreground">
            先给出结论，再展示明细表格
          </p>
        </div>
      </div>
    </div>
  )
}
