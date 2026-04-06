"use client"

import { cn } from "@/lib/utils"
import { Sparkles } from "lucide-react"

interface ExamplePromptsProps {
  onSelect: (prompt: string) => void
  disabled: boolean
}

const EXAMPLE_PROMPTS = [
  "统计去年各地区的销售总额",
  "统计华东地区销售总额",
  "按品牌统计销售额",
  "统计不同会员等级的客单价",
  "查询本月销量前10的商品",
  "分析各渠道的转化率",
]

export function ExamplePrompts({ onSelect, disabled }: ExamplePromptsProps) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Sparkles className="w-4 h-4" />
        <span>示例问题</span>
      </div>
      <div className="flex flex-wrap gap-2">
        {EXAMPLE_PROMPTS.map((prompt) => (
          <button
            key={prompt}
            onClick={() => onSelect(prompt)}
            disabled={disabled}
            className={cn(
              "px-3 py-1.5 text-sm rounded-full",
              "bg-secondary/50 border border-border",
              "text-muted-foreground hover:text-foreground",
              "hover:bg-secondary hover:border-primary/30",
              "transition-all duration-200",
              "disabled:opacity-50 disabled:cursor-not-allowed",
              "focus:outline-none focus:ring-2 focus:ring-primary/20"
            )}
          >
            {prompt}
          </button>
        ))}
      </div>
    </div>
  )
}
