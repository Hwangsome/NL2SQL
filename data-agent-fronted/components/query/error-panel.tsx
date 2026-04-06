"use client"

import { Button } from "@/components/ui/button"
import { AlertCircle, RefreshCw } from "lucide-react"

interface ErrorPanelProps {
  message: string
  onRetry: () => void
  isLoading: boolean
}

export function ErrorPanel({ message, onRetry, isLoading }: ErrorPanelProps) {
  return (
    <div className="bg-destructive/5 border border-destructive/20 rounded-lg p-4 sm:p-6">
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0">
          <div className="w-10 h-10 rounded-full bg-destructive/10 flex items-center justify-center">
            <AlertCircle className="w-5 h-5 text-destructive" />
          </div>
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold text-destructive mb-1">
            查询失败
          </h3>
          <p className="text-sm text-muted-foreground leading-relaxed break-words">
            {message}
          </p>
          <Button
            variant="outline"
            size="sm"
            onClick={onRetry}
            disabled={isLoading}
            className="mt-3 gap-2 border-destructive/30 text-destructive hover:bg-destructive/10 hover:text-destructive"
          >
            <RefreshCw className="w-4 h-4" />
            重试
          </Button>
        </div>
      </div>
    </div>
  )
}
