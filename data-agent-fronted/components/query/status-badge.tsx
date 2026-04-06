"use client"

import type { ConnectionStatus } from "@/lib/types"
import { cn } from "@/lib/utils"
import { Loader2, CheckCircle2, XCircle } from "lucide-react"

interface StatusBadgeProps {
  status: ConnectionStatus
}

const statusConfig: Record<ConnectionStatus, {
  label: string
  className: string
  Icon: typeof Loader2
}> = {
  checking: {
    label: "检测中",
    className: "bg-warning/10 text-warning border-warning/20",
    Icon: Loader2,
  },
  connected: {
    label: "已连接",
    className: "bg-success/10 text-success border-success/20",
    Icon: CheckCircle2,
  },
  disconnected: {
    label: "未连接",
    className: "bg-destructive/10 text-destructive border-destructive/20",
    Icon: XCircle,
  },
}

export function StatusBadge({ status }: StatusBadgeProps) {
  const config = statusConfig[status]
  const { Icon, label, className } = config

  return (
    <div
      className={cn(
        "flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border",
        className
      )}
    >
      <Icon 
        className={cn(
          "w-3.5 h-3.5",
          status === "checking" && "animate-spin"
        )} 
      />
      <span>{label}</span>
    </div>
  )
}
