"use client"

import dynamic from "next/dynamic"
import { Spinner } from "@/components/ui/spinner"

// 使用 dynamic import 禁用 SSR，避免浏览器扩展导致的 hydration mismatch
const QueryWorkspace = dynamic(
  () => import("@/components/query/query-workspace").then((mod) => ({ default: mod.QueryWorkspace })),
  {
    ssr: false,
    loading: () => (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <Spinner className="w-8 h-8 text-primary" />
          <p className="text-muted-foreground text-sm">加载中...</p>
        </div>
      </div>
    ),
  }
)

export default function HomePage() {
  return <QueryWorkspace />
}
