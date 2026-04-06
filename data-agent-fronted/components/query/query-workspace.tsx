"use client"

import { useState, useEffect, useCallback, useRef } from "react"
import {
  Header,
  QueryComposer,
  ExamplePrompts,
  ConversationTurn,
  WelcomeState,
} from "@/components/query"
import { streamQuery, checkHealth } from "@/lib/stream-query"
import type { ConnectionStatus, ConversationTurn as ConversationTurnType, ProgressStep, StreamEvent } from "@/lib/types"

export function QueryWorkspace() {
  const [query, setQuery] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>("checking")
  const [turns, setTurns] = useState<ConversationTurnType[]>([])

  const abortControllerRef = useRef<AbortController | null>(null)
  const lastQueryRef = useRef("")
  const activeTurnIdRef = useRef<string | null>(null)
  const scrollAnchorRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const checkConnection = async () => {
      setConnectionStatus("checking")
      const isHealthy = await checkHealth()
      setConnectionStatus(isHealthy ? "connected" : "disconnected")
    }

    checkConnection()
    const interval = setInterval(checkConnection, 30000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    scrollAnchorRef.current?.scrollIntoView({ behavior: "smooth", block: "end" })
  }, [turns])

  const updateActiveTurn = useCallback((updater: (turn: ConversationTurnType) => ConversationTurnType) => {
    const activeTurnId = activeTurnIdRef.current
    if (!activeTurnId) return

    setTurns((prev) =>
      prev.map((turn) => (turn.id === activeTurnId ? updater(turn) : turn))
    )
  }, [])

  const handleStreamEvent = useCallback((event: StreamEvent) => {
    switch (event.type) {
      case "progress":
        updateActiveTurn((turn) => {
          const existingIndex = turn.progressSteps.findIndex((step) => step.step === event.step)
          const progressSteps = [...turn.progressSteps]
          if (existingIndex >= 0) {
            progressSteps[existingIndex] = { step: event.step, status: event.status, detail: event.detail }
          } else {
            progressSteps.push({ step: event.step, status: event.status, detail: event.detail })
          }
          return { ...turn, progressSteps }
        })
        break

      case "answer":
        updateActiveTurn((turn) => ({ ...turn, answer: turn.answer + event.delta }))
        break

      case "result":
        updateActiveTurn((turn) => ({
          ...turn,
          answer: event.answer ?? turn.answer,
          sql: event.sql ?? turn.sql,
          resultRows: event.data,
          isStreaming: false,
        }))
        abortControllerRef.current = null
        activeTurnIdRef.current = null
        setIsLoading(false)
        break

      case "error":
        updateActiveTurn((turn) => ({ ...turn, errorMessage: event.message, isStreaming: false }))
        abortControllerRef.current = null
        activeTurnIdRef.current = null
        setIsLoading(false)
        break
    }
  }, [updateActiveTurn])

  const runQuery = useCallback(async (nextQuery: string) => {
    const normalizedQuery = nextQuery.trim()
    if (!normalizedQuery || isLoading) return

    const turnId = typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now()}`

    lastQueryRef.current = normalizedQuery
    activeTurnIdRef.current = turnId
    abortControllerRef.current = new AbortController()
    setIsLoading(true)
    setQuery("")
    setTurns((prev) => [
      ...prev,
      {
        id: turnId,
        query: normalizedQuery,
        progressSteps: [],
        answer: "",
        resultRows: [],
        sql: "",
        errorMessage: "",
        isStreaming: true,
      },
    ])

    try {
      await streamQuery(normalizedQuery, handleStreamEvent, abortControllerRef.current.signal)
    } catch (error) {
      if (error instanceof Error) {
        if (error.name === "AbortError") {
          updateActiveTurn((turn) => ({
            ...turn,
            isStreaming: false,
            progressSteps: [
              ...turn.progressSteps,
              { step: "查询已取消", status: "error", detail: "用户主动停止了本次查询。" },
            ],
            answer: turn.answer || "本次回答已中止，你可以继续追问或重新发起查询。",
          }))
        } else {
          updateActiveTurn((turn) => ({
            ...turn,
            errorMessage: error.message || "请求失败，请检查网络连接",
            isStreaming: false,
          }))
        }
      } else {
        updateActiveTurn((turn) => ({
          ...turn,
          errorMessage: "发生未知错误",
          isStreaming: false,
        }))
      }
      activeTurnIdRef.current = null
      abortControllerRef.current = null
      setIsLoading(false)
    }
  }, [handleStreamEvent, isLoading, updateActiveTurn])

  const handleSubmit = useCallback(async () => {
    await runQuery(query)
  }, [query, runQuery])

  const handleStop = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }
    setIsLoading(false)
  }, [])

  const handleClearSession = useCallback(() => {
    setQuery("")
    setTurns([])
    lastQueryRef.current = ""
    activeTurnIdRef.current = null
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }
    setIsLoading(false)
  }, [])

  // 选择示例问题
  const handleSelectExample = useCallback((prompt: string) => {
    setQuery(prompt)
  }, [])

  const handleRetry = useCallback((retryQuery?: string) => {
    const nextQuery = retryQuery ?? lastQueryRef.current
    if (!nextQuery) return
    void runQuery(nextQuery)
  }, [runQuery])

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Header
        connectionStatus={connectionStatus}
        onClearSession={handleClearSession}
        isLoading={isLoading}
      />

      <main className="mx-auto min-h-[calc(100vh-4rem)] max-w-5xl px-4 pb-44 pt-6 sm:px-6 sm:pt-8 lg:px-8">
        <section className="relative overflow-hidden rounded-[32px] border border-border bg-card/75 p-5 shadow-[0_50px_120px_-80px_rgba(0,0,0,0.95)] sm:p-6">
          <div className="pointer-events-none absolute inset-x-0 top-0 h-32 bg-[radial-gradient(circle_at_top,rgba(38,211,199,0.18),transparent_55%)]" />

          <div className="relative space-y-6">
            {turns.length === 0 ? (
              <>
                <WelcomeState />
                <ExamplePrompts onSelect={handleSelectExample} disabled={isLoading} />
              </>
            ) : (
              <div className="space-y-8">
                {turns.map((turn) => (
                  <ConversationTurn key={turn.id} turn={turn} onRetry={handleRetry} />
                ))}
                <div ref={scrollAnchorRef} />
              </div>
            )}
          </div>
        </section>
      </main>

      <div className="fixed inset-x-0 bottom-0 z-40 border-t border-border/80 bg-background/88 backdrop-blur-xl">
        <div className="mx-auto max-w-5xl px-4 py-4 sm:px-6 lg:px-8">
          <div className="rounded-[30px] border border-border bg-card/90 p-4 shadow-[0_30px_90px_-70px_rgba(0,0,0,0.95)]">
            <QueryComposer
              query={query}
              onQueryChange={setQuery}
              onSubmit={handleSubmit}
              onStop={handleStop}
              isLoading={isLoading}
              disabled={connectionStatus === "disconnected"}
            />

            <div className="mt-4 border-t border-border/70 pt-4">
              <ExamplePrompts onSelect={handleSelectExample} disabled={isLoading} />
            </div>
          </div>

          <div className="mt-3 text-center">
            <p className="text-xs text-muted-foreground">
              掌柜问数 · 一问一答式数据分析助手
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
