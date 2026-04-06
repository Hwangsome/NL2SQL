"use client"

import { Button } from "@/components/ui/button"
import { StatusBadge } from "./status-badge"
import type { ConnectionStatus } from "@/lib/types"
import { Database, RotateCcw } from "lucide-react"

interface HeaderProps {
  connectionStatus: ConnectionStatus
  onClearSession: () => void
  isLoading: boolean
}

export function Header({ connectionStatus, onClearSession, isLoading }: HeaderProps) {
  return (
    <header className="border-b border-border bg-card/50 backdrop-blur-sm sticky top-0 z-50">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo and Title */}
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-primary/10 border border-primary/20">
              <Database className="w-5 h-5 text-primary" />
            </div>
            <div className="flex flex-col">
              <h1 className="text-lg font-semibold text-foreground tracking-tight">
                掌柜问数
              </h1>
              <p className="text-xs text-muted-foreground hidden sm:block">
                用自然语言查询业务数据
              </p>
            </div>
          </div>

          {/* Right Section */}
          <div className="flex items-center gap-3">
            <StatusBadge status={connectionStatus} />
            <Button
              variant="outline"
              size="sm"
              onClick={onClearSession}
              disabled={isLoading}
              className="gap-2 text-muted-foreground hover:text-foreground"
            >
              <RotateCcw className="w-4 h-4" />
              <span className="hidden sm:inline">清空会话</span>
            </Button>
          </div>
        </div>
      </div>
    </header>
  )
}
