"use client"

import { Database, Sparkles } from "lucide-react"

import { ErrorPanel } from "./error-panel"
import { ProgressTimeline } from "./progress-timeline"
import { ResultVisualization } from "./result-visualization"
import { ResultTable } from "./result-table"
import type { ConversationTurn } from "@/lib/types"
import { cn } from "@/lib/utils"

interface ConversationTurnProps {
  turn: ConversationTurn
  onRetry: (query: string) => void
}

export function ConversationTurn({ turn, onRetry }: ConversationTurnProps) {
  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <div className="max-w-[90%] rounded-[24px] rounded-br-md border border-primary/25 bg-primary px-5 py-4 text-primary-foreground shadow-[0_10px_40px_-20px_rgba(38,211,199,0.85)]">
          <p className="text-[11px] uppercase tracking-[0.22em] text-primary-foreground/70">你</p>
          <p className="mt-2 whitespace-pre-wrap text-sm leading-7 sm:text-[15px]">{turn.query}</p>
        </div>
      </div>

      <div className="flex items-start gap-3 sm:gap-4">
        <div className="mt-1 flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border border-primary/20 bg-card text-primary">
          <Database className="h-5 w-5" />
        </div>

        <div className="min-w-0 flex-1 space-y-3">
          <div className="overflow-hidden rounded-[28px] rounded-tl-md border border-border bg-card/95 shadow-[0_30px_90px_-60px_rgba(0,0,0,0.95)]">
            <div className="border-b border-border/80 bg-secondary/35 px-5 py-3">
              <div className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-primary" />
                <p className="text-sm font-semibold text-foreground">掌柜问数</p>
              </div>
            </div>

            <div className="space-y-4 px-5 py-5 sm:px-6">
              <div className="space-y-3">
                <p className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground">结论</p>
                <div className="rounded-2xl border border-border/70 bg-background/55 px-4 py-4">
                  {turn.answer ? (
                    <p className="whitespace-pre-wrap text-sm leading-7 text-foreground sm:text-[15px]">
                      {turn.answer}
                      {turn.isStreaming && (
                        <span className="ml-1 inline-block h-5 w-2 animate-pulse rounded-full bg-primary/70 align-middle" />
                      )}
                    </p>
                  ) : (
                    <p className="text-sm leading-7 text-muted-foreground">
                      {turn.errorMessage ? "本次回答生成失败。" : "正在整理结论，请稍候..."}
                    </p>
                  )}
                </div>
              </div>

              {turn.sql && (
                <details className="group rounded-2xl border border-border/70 bg-background/40 px-4 py-3">
                  <summary className="cursor-pointer list-none text-sm font-medium text-foreground">
                    查看 SQL
                  </summary>
                  <pre className="mt-3 overflow-x-auto whitespace-pre-wrap break-all rounded-xl bg-secondary/35 p-3 font-mono text-xs leading-6 text-muted-foreground">
                    {turn.sql}
                  </pre>
                </details>
              )}

              {turn.errorMessage ? (
                <ErrorPanel message={turn.errorMessage} onRetry={() => onRetry(turn.query)} isLoading={turn.isStreaming} />
              ) : null}

              {(turn.resultRows.length > 0 || (!turn.isStreaming && turn.progressSteps.length > 0 && !turn.errorMessage)) && (
                <div className="space-y-3">
                  <p className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground">数据</p>
                  <ResultVisualization data={turn.resultRows} />
                  <ResultTable data={turn.resultRows} />
                </div>
              )}
            </div>
          </div>

          {turn.progressSteps.length > 0 && (
            <div className={cn("transition-opacity", turn.isStreaming ? "opacity-100" : "opacity-85")}>
              <ProgressTimeline steps={turn.progressSteps} />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
