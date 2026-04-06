"use client"

import { useState } from "react"
import type { ProgressStep } from "@/lib/types"
import { cn } from "@/lib/utils"
import { CheckCircle2, XCircle, Loader2, Circle, ChevronDown } from "lucide-react"

interface ProgressTimelineProps {
  steps: ProgressStep[]
}

const statusConfig = {
  running: {
    Icon: Loader2,
    className: "text-primary",
    dotClassName: "bg-primary/20 border-primary",
    lineClassName: "bg-primary/30",
    iconAnimation: "animate-spin",
  },
  success: {
    Icon: CheckCircle2,
    className: "text-success",
    dotClassName: "bg-success/20 border-success",
    lineClassName: "bg-success/50",
    iconAnimation: "",
  },
  error: {
    Icon: XCircle,
    className: "text-destructive",
    dotClassName: "bg-destructive/20 border-destructive",
    lineClassName: "bg-destructive/50",
    iconAnimation: "",
  },
}

export function ProgressTimeline({ steps }: ProgressTimelineProps) {
  const [expandedSteps, setExpandedSteps] = useState<Record<string, boolean>>({})

  if (steps.length === 0) {
    return null
  }

  const toggleStep = (key: string) => {
    setExpandedSteps((prev) => ({ ...prev, [key]: !prev[key] }))
  }

  return (
    <div className="bg-card border border-border rounded-lg p-4 sm:p-6">
      <h3 className="text-sm font-medium text-foreground mb-4 flex items-center gap-2">
        <Circle className="w-4 h-4 text-primary" />
        执行进度
      </h3>
      
      <div className="space-y-0">
        {steps.map((step, index) => {
          const config = statusConfig[step.status]
          const { Icon } = config
          const isLast = index === steps.length - 1
          const stepKey = `${step.step}-${index}`
          const isExpanded = Boolean(expandedSteps[stepKey])

          return (
            <div key={stepKey} className="relative flex items-start gap-3">
              {/* 连接线 */}
              {!isLast && (
                <div
                  className={cn(
                    "absolute left-[11px] top-6 w-0.5 h-full -ml-px",
                    step.status === "success" 
                      ? "bg-success/30" 
                      : step.status === "error"
                      ? "bg-destructive/30"
                      : "bg-border"
                  )}
                />
              )}
              
              {/* 图标 */}
              <div
                className={cn(
                  "relative z-10 flex items-center justify-center w-6 h-6 rounded-full border-2",
                  config.dotClassName
                )}
              >
                <Icon
                  className={cn(
                    "w-3.5 h-3.5",
                    config.className,
                    config.iconAnimation
                  )}
                />
              </div>

              {/* 步骤内容 */}
              <div className="flex-1 min-w-0 pb-4">
                <button
                  type="button"
                  onClick={() => toggleStep(stepKey)}
                  className={cn(
                    "flex w-full items-start justify-between gap-3 rounded-xl text-left transition-colors",
                    step.detail && "hover:bg-secondary/20"
                  )}
                  disabled={!step.detail}
                >
                  <div className="min-w-0">
                    <div
                      className={cn(
                        "text-sm font-medium",
                        step.status === "running" && "text-foreground",
                        step.status === "success" && "text-muted-foreground",
                        step.status === "error" && "text-destructive"
                      )}
                    >
                      {step.step}
                    </div>
                    <div
                      className={cn(
                        "text-xs mt-0.5",
                        step.status === "running" && "text-primary",
                        step.status === "success" && "text-success/70",
                        step.status === "error" && "text-destructive/70"
                      )}
                    >
                      {step.status === "running" && "处理中..."}
                      {step.status === "success" && "已完成"}
                      {step.status === "error" && "执行失败"}
                      {step.detail && " · 点击查看详情"}
                    </div>
                  </div>
                  {step.detail ? (
                    <ChevronDown
                      className={cn(
                        "mt-0.5 h-4 w-4 shrink-0 text-muted-foreground transition-transform",
                        isExpanded && "rotate-180"
                      )}
                    />
                  ) : null}
                </button>
                {step.detail && isExpanded ? (
                  <div className="mt-2 rounded-xl border border-border/70 bg-background/55 px-3 py-2 text-xs leading-6 text-muted-foreground whitespace-pre-wrap">
                    {step.detail}
                  </div>
                ) : null}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
