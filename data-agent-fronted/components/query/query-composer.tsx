"use client"

import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Search, Square, Loader2 } from "lucide-react"
import { useCallback, type KeyboardEvent } from "react"

interface QueryComposerProps {
  query: string
  onQueryChange: (query: string) => void
  onSubmit: () => void
  onStop: () => void
  isLoading: boolean
  disabled: boolean
}

export function QueryComposer({
  query,
  onQueryChange,
  onSubmit,
  onStop,
  isLoading,
  disabled,
}: QueryComposerProps) {
  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      // Enter 提交，Shift+Enter 换行
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault()
        if (!isLoading && !disabled && query.trim()) {
          onSubmit()
        }
      }
    },
    [isLoading, disabled, query, onSubmit]
  )

  return (
    <div className="space-y-3">
      <div className="relative">
        <Textarea
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入一个业务问题，系统会像分析师一样边推理边给你回答，例如：统计去年各地区的销售总额"
          className="min-h-[112px] resize-none rounded-3xl border-border bg-secondary/45 px-5 py-4 text-base leading-relaxed placeholder:text-muted-foreground/60 focus:border-primary/50 focus:ring-primary/20"
          disabled={isLoading}
        />
        <div className="absolute bottom-3 right-3 text-xs text-muted-foreground/60">
          <kbd className="px-1.5 py-0.5 rounded bg-muted/50 border border-border text-[10px]">
            Enter
          </kbd>
          <span className="mx-1">提交</span>
          <kbd className="px-1.5 py-0.5 rounded bg-muted/50 border border-border text-[10px]">
            Shift + Enter
          </kbd>
          <span className="ml-1">换行</span>
        </div>
      </div>

      <div className="flex gap-2">
        <Button
          onClick={onSubmit}
          disabled={isLoading || disabled || !query.trim()}
          className="gap-2 bg-primary hover:bg-primary/90 text-primary-foreground"
        >
          {isLoading ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              查询中...
            </>
          ) : (
            <>
              <Search className="w-4 h-4" />
              开始查询
            </>
          )}
        </Button>

        {isLoading && (
          <Button
            variant="outline"
            onClick={onStop}
            className="gap-2 border-destructive/30 text-destructive hover:bg-destructive/10 hover:text-destructive"
          >
            <Square className="w-4 h-4" />
            停止生成
          </Button>
        )}
      </div>
    </div>
  )
}
